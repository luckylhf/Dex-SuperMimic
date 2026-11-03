"""Render saved ROS trajectories only; no simulation stepping or policy training."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = None
CONFIG = None
import os
FONT = os.environ.get('DEX_VIDEO_FONT', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
BG = (15, 21, 31)
TEXT = (232, 237, 245)
COLORS = [(169, 183, 204), (65, 211, 172), (255, 161, 92)]
W, H, FPS = 1920, 1080, 25


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_run(folder, motion, iteration):
    report_path = folder / (motion + '_' + CONFIG.get('transport','ros') + '.json')
    report = json.loads(report_path.read_text())
    bundle = folder / 'development/bundle'
    contract = json.loads((bundle / 'contract.json').read_text())
    with np.load(report['trajectory'], allow_pickle=False) as z:
        assert str(z['policy_sha256']) == report['policy_sha256'] == contract['policy_sha256']
        assert str(z['model_sha256']) == report['model_sha256'] == contract['model_sha256']
        assert str(z['reference_source_sha256']) == report['reference']['source_sha256']
        assert float(z['control_dt']) == .02
        poses = z['qpos'].copy()
    assert sha(bundle / 'policy.onnx') == contract['policy_sha256']
    assert len(poses) == len(report['metrics']) + 1
    assert abs((len(poses)-1)*.02 - report['elapsed_seconds']) < 1e-6
    return dict(report=report, report_path=str(report_path), contract=contract,
                bundle=bundle, poses=poses, iteration=iteration,
                trajectory_sha256=sha(report['trajectory']))


def make(motion, preview_only):
    OUT.mkdir(exist_ok=True, parents=True)
    conf = CONFIG['motions'][motion]
    name = {'gbtc':'GBTC 广播体操','dance_boy':'dance-boy 舞蹈','dance_girl':'dance-girl 长舞蹈'}.get(motion, motion)
    best_it = conf['best_iteration']
    latest_it = CONFIG['latest_iteration']
    reference = Path(conf['reference'])
    selection = '最佳口径：完成优先；失败时长差小于0.1秒时比较位置误差'
    runs = [read_run(Path(conf['best_folder']), motion, best_it),
            read_run(Path(CONFIG['latest_folder']), motion, latest_it)]
    with np.load(reference, allow_pickle=False) as z:
        ref = {k: z[k].copy() for k in z.files if k != 'metadata'}
        metadata = json.loads(str(z['metadata']))
    for run in runs:
        assert run['report']['reference']['source_sha256'] == metadata['source_sha256']
        assert run['contract']['model_sha256'] == metadata['model_sha256']
        assert run['contract']['joint_names'] == metadata['joint_names']
    assert sha(runs[0]['bundle'] / 'model.mjb') == sha(runs[1]['bundle'] / 'model.mjb')
    model = mujoco.MjModel.from_binary_path(str(runs[0]['bundle'] / 'model.mjb'))
    model.vis.global_.offwidth = 640
    model.vis.global_.offheight = 480
    renderer = mujoco.Renderer(model, height=480, width=640)
    datas = [mujoco.MjData(model) for _ in range(3)]
    qadr = [model.jnt_qposadr[model.joint('robot/'+n).id] for n in metadata['joint_names']]
    free = int(np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)[0])
    rq = int(model.jnt_qposadr[free])
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.distance = 3.25
    camera.azimuth = 130
    camera.elevation = -12
    fonts = {s: ImageFont.truetype(FONT, s) for s in [20, 23, 26, 28, 34]}
    max_f = max(len(r['poses']) for r in runs)-1
    for r in runs:
        r['root_max'] = max(m['root_error_m'] for m in r['report']['metrics'])
        r['body_mean'] = sum(m['body_global_rmse_m'] for m in r['report']['metrics'])/len(r['report']['metrics'])
    paths = [ref['root_p'][:max_f+1, :2]] + [r['poses'][:, rq:rq+2] for r in runs]
    all_xy = np.concatenate(paths)
    lo, hi = all_xy.min(0), all_xy.max(0)
    mid = (lo+hi)/2
    # Equal scale on x/y, fixed bounds throughout playback; cameras above follow each pelvis.
    plot = (65, 780, 835, 1030)
    scale = min((plot[2]-plot[0])/max(1., float(hi[0]-lo[0])+1.),
                (plot[3]-plot[1])/max(1., float(hi[1]-lo[1])+1.))

    def xy(v):
        return (int((plot[0]+plot[2])/2 + (v[0]-mid[0])*scale),
                int((plot[1]+plot[3])/2 - (v[1]-mid[1])*scale))

    def draw_text(draw, pos, value, size=26, color=TEXT):
        draw.text(pos, value, font=fonts[size], fill=color)

    def frame(f):
        t = f*.02
        canvas = Image.new('RGB', (W, H), BG)
        draw = ImageDraw.Draw(canvas)
        draw_text(draw, (24, 12), name+'  |  '+CONFIG['latest_label']+' · 最佳与最新', 34)
        draw_text(draw, (1450, 20), f'同步时间 {t:05.2f} 秒', 28)
        titles = ['参考动作（运动学）', f'历史最佳 · 第 {best_it:,} 次', f'最新 · 第 {latest_it:,} 次']
        if conf['same_model']: titles[1] += '（与最新相同）'
        for col in range(3):
            x = col*640
            data = datas[col]
            stopped = False
            if col == 0:
                data.qpos[:] = runs[0]['poses'][0]
                data.qpos[qadr] = ref['q'][f]
                data.qpos[rq:rq+3] = ref['root_p'][f]
                quat = np.zeros(4)
                mujoco.mju_mat2Quat(quat, ref['root_R'][f].astype(np.float64).reshape(9))
                data.qpos[rq+3:rq+7] = quat
            else:
                run = runs[col-1]
                idx = min(f, len(run['poses'])-1)
                data.qpos[:] = run['poses'][idx]
                stopped = bool(run['report']['failed'] and f >= len(run['poses'])-1)
            mujoco.mj_forward(model, data)
            camera.lookat[:] = [data.qpos[rq], data.qpos[rq+1], .88]
            renderer.update_scene(data, camera)
            rendered = Image.fromarray(renderer.render().copy())
            if stopped:
                rendered = Image.blend(rendered, Image.new('RGB', rendered.size, (36, 13, 13)), .30)
            canvas.paste(rendered, (x, 112))
            draw.rectangle((x+1, 64, x+639, 111), fill=tuple(int(v*.22) for v in COLORS[col]))
            draw_text(draw, (x+18, 70), titles[col], 23, COLORS[col])
            if col == 0:
                draw_text(draw, (x+18, 604), f'完整参考：{(len(ref["q"])-1)*.02:.2f} 秒', 26)
                draw_text(draw, (x+18, 643), '上方镜头跟随各自骨盆，便于看清姿态', 23)
            else:
                run = runs[col-1]
                err = run['report']['metrics'][idx-1] if idx else {'root_error_m': 0., 'joint_rmse_rad': 0.}
                draw_text(draw, (x+18, 604), f'当前位置偏差 {err["root_error_m"]:.2f} 米', 28, COLORS[col])
                draw_text(draw, (x+18, 643), f'关节误差 {err["joint_rmse_rad"]:.3f} rad', 23)
                if stopped:
                    draw.rectangle((x+18, 492, x+622, 574), fill=(109, 28, 30))
                    draw_text(draw, (x+32, 499), f'{run["report"]["elapsed_seconds"]:.2f} 秒触发终止', 28)
                    draw_text(draw, (x+32, 538), '此处起定格，后续未继续仿真', 23)
        draw.line((0, 694, W, 694), fill=(61, 75, 94), width=2)
        draw_text(draw, (24, 705), '骨盆轨迹俯视图 · 同一世界坐标 · 米', 26)
        draw_text(draw, (24, 742), '灰：参考    绿：历史最佳    橙：最新', 20)
        draw.rectangle(plot, fill=(23, 32, 44), outline=(75, 87, 102), width=1)
        unit = 1 if max(hi-lo) < 5 else 5
        x_min = mid[0]-(plot[2]-plot[0])/2/scale
        x_max = mid[0]+(plot[2]-plot[0])/2/scale
        y_min = mid[1]-(plot[3]-plot[1])/2/scale
        y_max = mid[1]+(plot[3]-plot[1])/2/scale
        for v in range(math.ceil(x_min/unit), math.floor(x_max/unit)+1):
            px = xy([v*unit, mid[1]])[0]
            draw.line((px, plot[1], px, plot[3]), fill=(43, 55, 70))
            draw_text(draw, (px+3, plot[3]+2), str(v*unit), 20)
        for v in range(math.ceil(y_min/unit), math.floor(y_max/unit)+1):
            py = xy([mid[0], v*unit])[1]
            draw.line((plot[0], py, plot[2], py), fill=(43, 55, 70))
            draw_text(draw, (plot[0]-40, py-13), str(v*unit), 20)
        for path, color in zip(paths, COLORS):
            points = [xy(v) for v in path[:min(f+1, len(path))]]
            if len(points)>1: draw.line(points, fill=color, width=3)
            px, py = points[-1]
            draw.ellipse((px-5, py-5, px+5, py+5), fill=color)
        draw_text(draw, (910, 712), selection, 23)
        draw_text(draw, (910, 1039), '最佳来源：'+conf.get('best_label', Path(conf['best_folder']).name)+'；最新：'+CONFIG['latest_label'], 20)
        for i, run in enumerate(runs):
            root_max = run['root_max']
            body_mean = run['body_mean']
            elapsed = run['report']['elapsed_seconds']
            y = 760+i*100
            label = '历史最佳' if i == 0 else '最新'
            outcome = '完整播放' if run['report']['completed'] else '触发终止'
            draw_text(draw, (910, y), f'{label}：{elapsed:.2f} 秒 {outcome}', 28, COLORS[i+1])
            draw_text(draw, (910, y+41), f'全段最大位置偏差 {root_max:.2f} 米  |  平均全身误差 {body_mean:.2f} 米', 23)
        draw_text(draw, (910, 969), ('ROS + MuJoCo' if CONFIG.get('transport','ros') == 'ros' else '原生 MuJoCo') + ' 已记录轨迹；1 倍速；无支撑、无中途重置', 23)
        note = ('零次训练：含参考关节前馈，未进行任何参数优化' if latest_it == 0 else '开发评测；动作可完成不等于跟踪精度已验收')
        if CONFIG.get('evaluation_profile') == 'height_diagnostic_v1':
            note = '高度超差仅记录，倾斜超差仍终止；播完不等于跟踪合格'
        draw_text(draw, (910, 1010), note, 23, (255, 195, 135))
        return canvas

    stem = motion+'_best_vs_latest'
    previews = sorted(set([0, min(250, max_f), min(460, max_f), max_f]))
    try:
        if preview_only:
            for f in previews: frame(f).save(OUT/f'{stem}_{f:04d}.png')
        else:
            output = OUT/(stem+'.mp4')
            with imageio.get_writer(output, fps=FPS, codec='libx264', quality=8,
                                    macro_block_size=2, ffmpeg_params=['-movflags', '+faststart', '-pix_fmt', 'yuv420p']) as writer:
                for f in range(0, max_f+1, 2):
                    im = frame(f)
                    writer.append_data(np.asarray(im))
                    if f in previews: im.save(OUT/f'{stem}_{f:04d}.png')
                    if f % 200 == 0: print(motion, 'rendered', f, '/', max_f, flush=True)
                # Explicit end hold; the on-screen time does not advance.
                im = frame(max_f)
                d = ImageDraw.Draw(im)
                d.rectangle((1430, 0, 1919, 62), fill=BG)
                draw_text(d, (1440, 15), f'回放结束 · {max_f*.02:.2f} 秒', 28)
                for _ in range(FPS): writer.append_data(np.asarray(im))
            evidence = {'motion': motion, 'selection_rule': selection,
                        'reference': str(reference), 'reference_sha256': sha(reference),
                        'video': str(output), 'video_sha256': sha(output), 'fps': FPS,
                        'rendered_simulation_seconds': max_f*.02, 'end_hold_seconds': 1,
                        'camera': 'same distance and orientation, each tracks own pelvis; fixed equal-scale world XY plot exposes drift',
                        'termination_display': 'freeze and label after recorded termination, no extrapolated frames',
                        'runs': [{k:r[k] for k in ['iteration','report_path','trajectory_sha256']} for r in runs]}
            (OUT/(stem+'.json')).write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            print('VIDEO_READY', output, flush=True)
    finally:
        renderer.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview-only', action='store_true')
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    CONFIG = json.loads(Path(args.config).read_text())
    OUT = Path(CONFIG['out'])
    for motion in CONFIG['motions']: make(motion, args.preview_only)

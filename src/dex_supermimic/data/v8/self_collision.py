"""CPU arm self-collision scan and bounded local trajectory recovery.

Mink supplies signed-distance displacement Jacobians. Already penetrating input
needs an additional recovery bound; Mink's normal approach limit alone cannot
remove it. Only checked windows are committed, and unresolved motion is graded B.
This covers the declared arm/torso/hip/head/opposite-arm pairs, not all contacts.
"""
import copy
import time
import numpy as np
import mujoco
from scipy import sparse as sp
from scipy.spatial.transform import Rotation
from .arms import ArmObjective

POLICY = 'mink_arm_local_recovery_v1'
DEFAULTS = dict(enabled=True, margin_m=.0035, detection_m=.08,
                penetration_tolerance_m=1e-5, padding_s=.32,
                max_window_s=3., max_iterations=24, interpolation_steps=4)


class CollisionModel:
    def __init__(self, robot, config=None):
        import mink
        self.r = robot
        self.cfg = dict(DEFAULTS, **(config or {}))
        if not (0 <= self.cfg['penetration_tolerance_m'] < self.cfg['margin_m'] < self.cfg['detection_m']):
            raise ValueError('Invalid self-collision distances')
        # Never mutate the shared read-only model used by batch workers.
        self.m = m = copy.copy(robot.m)
        ids = np.flatnonzero(m.geom_group == 1)
        self.arms = {}
        for side, suffix in [('Left', 'l'), ('Right', 'r')]:
            names = [f'{p}_{suffix}_link_collision' for p in
                     ('shoulder_yaw', 'elbow_pitch', 'elbow_yaw', 'wrist_pitch', 'wrist_roll')]
            names += [side.lower() + '_tcp_link_collision']
            available = {m.geom(i).name: int(i) for i in ids}
            if not set(names) <= available.keys():
                raise ValueError('Dex arm collision geometry missing: ' + str(set(names) - available.keys()))
            self.arms[side] = [available[name] for name in names]
        body = [int(i) for i in ids if i not in sum(self.arms.values(), [])
                and not any(n in m.geom(i).name for n in ('shoulder', 'ankle', 'knee'))]
        if not body:
            raise ValueError('Dex torso collision geometry missing')
        groups = [(self.arms[s], body) for s in self.arms]
        groups += [(self.arms['Left'], self.arms['Right'])]
        m.geom_contype[ids] = 1
        m.geom_conaffinity[ids] = 1
        self.limit = mink.CollisionAvoidanceLimit(m, groups,
            minimum_distance_from_collisions=self.cfg['margin_m'],
            collision_detection_distance=self.cfg['detection_m'])
        self.pairs = np.array(self.limit.geom_id_pairs, dtype=int)
        if not len(self.pairs):
            raise ValueError('Empty self-collision pair set')
        self.names = [[m.geom(a).name, m.geom(b).name] for a, b in self.pairs]
        self.configuration = mink.Configuration(m)

    def update(self, x, rotation):
        self.r.set(x, rotation)
        self.configuration.update(self.r.d.qpos)

    def distances(self):
        a, b = self.pairs.T
        m, data = self.m, self.configuration.data
        limit = self.cfg['detection_m']
        # Conservative bounding-sphere test; unbounded geoms always survive.
        bounded = (m.geom_rbound[a] > 0) & (m.geom_rbound[b] > 0)
        near = (~bounded) | (np.linalg.norm(data.geom_xpos[a]-data.geom_xpos[b], axis=1)
                            - m.geom_rbound[a]-m.geom_rbound[b] < limit)
        d = np.full(len(a), limit)
        for k in np.flatnonzero(near):
            d[k] = mujoco.mj_geomDistance(m, data, int(a[k]), int(b[k]), limit, None)
        return d

    def linear(self, columns):
        con = self.limit.compute_qp_inequalities(self.configuration, 1.)
        active = np.isfinite(con.h)
        d = self.distances()[active]
        # Retain Mink's approach damping outside the margin; demand recovery
        # inside it. G is displacement-based, so multiplying it by fps is wrong.
        upper = np.minimum(con.h[active], d-self.cfg['margin_m'])
        return con.G[active][:, self.r.cols[columns]], upper


def scan(model, xs, rotations, subdivisions=None):
    """Full exported trajectory, plus fixed subframe FK samples. Not a CCD proof."""
    xs = np.asarray(xs)
    if len(xs) != len(rotations) or not np.isfinite(xs).all() or not np.isfinite(rotations).all():
        raise ValueError('Invalid collision trajectory')
    steps = model.cfg['interpolation_steps'] if subdivisions is None else subdivisions
    if not isinstance(steps, int) or steps < 1:
        raise ValueError('interpolation_steps must be a positive integer')
    tol = model.cfg['penetration_tolerance_m']
    minimum = model.cfg['detection_m']; worst = None; events = []
    native = []; bad_intervals = set(); impacted = set()
    delta = Rotation.from_matrix(rotations[:-1].transpose(0,2,1) @ rotations[1:]).as_rotvec() if len(xs)>1 else []
    for i, x in enumerate(xs):
        for k in range(steps if i+1 < len(xs) else 1):
            alpha = k/steps
            rot = rotations[i] if k == 0 else rotations[i] @ Rotation.from_rotvec(delta[i]*alpha).as_matrix()
            model.update(x if k == 0 else x*(1-alpha)+xs[i+1]*alpha, rot)
            d = model.distances(); j = int(np.argmin(d)); value = float(d[j])
            if k == 0: native.append(value)
            if value < minimum:
                minimum = value; worst = dict(frame=i, fraction=alpha, pair=model.names[j], distance_m=value)
            bad = np.flatnonzero(d < -tol)
            if len(bad):
                impacted.add(i)
                if k: impacted.add(i+1); bad_intervals.add(i)
                events.append(dict(frame=i, fraction=alpha, pairs=bad.tolist(), minimum_m=value))
    report = dict(policy=POLICY, pair_count=len(model.pairs), frames=len(xs),
                  native_colliding_frames=int(np.sum(np.asarray(native)<-tol)),
                  interpolated_colliding_intervals=len(bad_intervals),
                  collision_samples=len(events), minimum_distance_m=minimum,
                  worst=worst, interpolation_steps=steps,
                  scope='arms versus torso/hips/head and opposite arm; convex geometry; not continuous collision certification')
    return report, events, impacted


def windows(impacted, n, padding):
    result = []
    for i in sorted(impacted):
        a, b = max(0,i-padding), min(n,i+padding+1)
        if result and a <= result[-1][1]: result[-1][1] = max(b,result[-1][1])
        else: result.append([a,b])
    return result


def _arm_bodies(robot, sides):
    roots = {int(robot.m.jnt_bodyid[np.flatnonzero(robot.m.jnt_dofadr == robot.dadr[robot.sides[s]['arm'][0]-3])[0]]) for s in sides}
    def belongs(body):
        while body:
            if body in roots: return True
            body = int(robot.m.body_parentid[body])
        return False
    return [b for b in robot.surface_models if belongs(b)]


def _repair_window(model, t, xs, solver_cfg, a, b, sides):
    import osqp
    r = model.r; cfg = model.cfg; n = b-a; fps = float(t['fps'])
    ids = np.array(sum([r.sides[s]['arm'] for s in sides], [])); width = len(ids)
    bodies = _arm_bodies(r, sides)
    # Preserve load-bearing/rolling/sliding arm support. Such scenes need a
    # coupled contact solver; this local arm-only stage must not release them.
    for contact in t.get('body_contacts', []):
        if contact['body'] in bodies and np.any(np.asarray(contact['mode'])[a:b] > 0):
            raise ValueError('active_arm_support_requires_coupled_repair')
    q0 = xs[a:b, ids].copy(); q = q0.copy()
    lo, hi = r.lower[ids]+1e-6, r.upper[ids]-1e-6
    step = r.joint_step(fps, solver_cfg)[ids-3]
    objs = [[ArmObjective(r,t,i,s,xs[i],solver_cfg) for s in sides] for i in range(a,b)]
    I = sp.eye(n*width, format='csc')
    D1 = sp.kron(sp.diags([-np.ones(n-1),np.ones(n-1)],[0,1],shape=(n-1,n)),sp.eye(width),format='csc')
    D2 = sp.kron(sp.diags([np.ones(n-2),-2*np.ones(n-2),np.ones(n-2)],[0,1,2],shape=(n-2,n)),sp.eye(width),format='csc')
    smooth = sp.vstack([D1*.18*(fps/60),D2*6*(fps/60)**2,I*.12],format='csc')
    def pose(q, j):
        x=xs[a+j].copy();x[ids]=q[j];return x
    def objective(q):
        residual=[];blocks=[]
        for frame, row in zip(objs,q):
            for k,o in enumerate(frame):
                res,J=o.evaluate(row[k*7:(k+1)*7]);residual.append(res);blocks.append(J)
        return np.concatenate(residual), sp.block_diag(blocks,format='csc')
    def floor_geometry(x, i, jacobian=False):
        r.set(x,t['root_r'][i]);values=[];rows=[]
        for body in bodies:
            hull=r.surface_models[body]['hull'];heights=hull@r.rot(body)[2]+r.point(body)[2]
            values.append(float(heights.min()))
            if jacobian and heights.min()<.10:
                for local in hull[np.argsort(heights)[:4]]:
                    J,_=r.jac(body,local);rows.append((-J[2,ids],float(r.point(body,local)[2])))
        return min(values,default=1.),rows
    def metrics(q):
        distances=[];ground=[]
        for j in range(n):
            x=pose(q,j);model.update(x,t['root_r'][a+j]);distances.append(model.distances())
            ground.append(floor_geometry(x,a+j)[0])
        res,_=objective(q);d=np.asarray(distances);z=np.asarray(ground)
        cost=float(res@res+np.linalg.norm(smooth@(q-q0).ravel())**2)
        violation=float(np.maximum(cfg['margin_m']-d,0).sum())
        merit=cost+1e5*violation+1e6*float(np.maximum(-z,0).sum())
        return merit,float(d.min()),float(z.min())
    history=[]
    for iteration in range(cfg['max_iterations']):
        residual,J=objective(q);H=J.T@J+smooth.T@smooth+I*.01
        gradient=J.T@residual+smooth.T@(smooth@(q-q0).ravel())
        blocks=[];bounds=[]
        for j in range(n):
            x=pose(q,j);model.update(x,t['root_r'][a+j]);C,upper=model.linear(ids)
            _,floor_rows=floor_geometry(x,a+j,True)
            if floor_rows:
                C=np.vstack([C,np.array([v[0] for v in floor_rows])]);upper=np.r_[upper,[v[1] for v in floor_rows]]
            blocks.append(sp.csc_matrix(C));bounds.append(upper)
        C=sp.block_diag(blocks,format='csc');upper=np.concatenate(bounds)
        lb=np.maximum(np.tile(lo,n)-q.ravel(),-.18);ub=np.minimum(np.tile(hi,n)-q.ravel(),.18)
        # Preserve both endpoint pose and endpoint velocity when joining an
        # unchanged prefix/suffix. At actual sequence boundaries allow repair.
        fixed=([0,1] if a>0 else [])+([n-2,n-1] if b<len(xs) else [])
        for j in fixed:lb[j*width:(j+1)*width]=ub[j*width:(j+1)*width]=q0[j]-q[j]
        A=sp.vstack([I,D1,C],format='csc')
        lower=np.r_[lb,-np.tile(step,n-1)-D1@q.ravel(),np.full(len(upper),-np.inf)]
        upper=np.r_[ub,np.tile(step,n-1)-D1@q.ravel(),upper]
        scale=1/np.maximum(np.sqrt(A.multiply(A).sum(axis=1)).A.ravel(),1e-9)
        A=(sp.diags(scale)@A).tocsc();lower*=scale;upper*=scale
        opt=osqp.OSQP();opt.setup(P=sp.triu(H,format='csc'),q=gradient,A=A,l=lower,u=upper,
            eps_abs=1e-7,eps_rel=1e-7,max_iter=20000,verbose=False,polishing=True)
        sol=opt.solve()
        if sol.info.status_val not in (1,2) or not np.isfinite(sol.x).all():
            raise ValueError('collision_qp_'+sol.info.status)
        at=A@sol.x
        if max(float(np.max(lower-at)),float(np.max(at-upper)))>1e-6:
            raise ValueError('collision_qp_constraint_residual')
        delta=sol.x.reshape(n,width);old=metrics(q);accepted=False
        for alpha in (1.,.5,.25,.125,.0625):
            trial=q+alpha*delta;new=metrics(trial)
            if new[0]<old[0]+1e-9:q=trial;accepted=True;break
        history.append(dict(iteration=iteration,accepted=accepted,minimum_m=new[1]))
        if not accepted:break
        if new[1]>=cfg['margin_m']-2e-6 and new[2]>=-1e-5 and abs(delta).max()<2e-4:break
    candidate=xs.copy();candidate[a:b,ids]=q
    # Validate the exact float32 joint representation later exported to PKL.
    candidate[a:b,ids]=candidate[a:b,ids].astype(np.float32).astype(float)
    q=candidate[a:b,ids];merit,dmin,zmin=metrics(q)
    if dmin<.003-2e-6 or zmin < -1e-5:raise ValueError('nonlinear_collision_or_floor_clearance')
    if np.any(q<lo-2e-6) or np.any(q>hi+2e-6):raise ValueError('arm_angle_limit')
    if np.any(abs(np.diff(candidate[max(0,a-1):min(len(xs),b+1),ids],axis=0))>step+2e-6):
        raise ValueError('arm_velocity_or_boundary_limit')
    checked,_,_=scan(model,candidate[max(0,a-1):min(len(xs),b+1)],t['root_r'][max(0,a-1):min(len(xs),b+1)])
    if checked['collision_samples']:raise ValueError('interpolated_collision')
    return candidate,dict(start=a,end=b,sides=sides,status='repaired',iterations=len(history),
                          minimum_m=dmin,interpolated_minimum_m=checked['minimum_distance_m'],
                          maximum_correction_deg=float(np.rad2deg(abs(q-q0)).max()))


def refine(robot, t, xs, solver_cfg, config=None, progress=None):
    cfg=dict(DEFAULTS,**(config or {}));start=time.perf_counter()
    if not cfg['enabled']:return xs,dict(policy=POLICY,status='disabled')
    model=CollisionModel(robot,cfg);before,events,impacted=scan(model,xs,t['root_r'])
    out=xs.copy();reports=[];fps=float(t['fps'])
    for a,b in windows(impacted,len(xs),max(2,round(cfg['padding_s']*fps))):
        if progress:progress(a,len(xs))
        relevant=[e for e in events if a<=e['frame']<b]
        pair_ids={k for e in relevant for k in e['pairs']}
        geoms={g for k in pair_ids for g in model.pairs[k]}
        sides=[s for s,group in model.arms.items() if geoms.intersection(group)]
        try:
            if b-a>max(3,round(cfg['max_window_s']*fps)):
                raise ValueError('window_exceeds_local_repair_budget')
            if b-a<3:raise ValueError('window_too_short')
            candidate,report=_repair_window(model,t,out,solver_cfg,a,b,sides)
            out=candidate
        except ValueError as error:
            report=dict(start=a,end=b,sides=sides,status='unresolved',reason=str(error))
        reports.append(report)
    after,_,_=scan(model,out,t['root_r']) if impacted else (before,None,None)
    return out,dict(policy=POLICY,status='completed',before=before,after=after,windows=reports,
                    config=cfg,elapsed_s=time.perf_counter()-start)


def audit_export(robot, payload, config=None):
    xs=np.c_[payload['root_pos'],payload['dof_pos']].astype(float)
    rotations=Rotation.from_quat(payload['root_rot']).as_matrix()
    return scan(CollisionModel(robot,config),xs,rotations)[0]

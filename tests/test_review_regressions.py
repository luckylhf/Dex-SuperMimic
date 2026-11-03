import argparse
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dex_supermimic.common import atomic, sha
from dex_supermimic.data.prepare import _convert, load_records, row_sha, source_row, training_rows
from dex_supermimic.evaluation import evaluate as evaluation
from dex_supermimic.training.lr_schedule import PolicyLRSchedule


@pytest.fixture
def cached(tmp_path):
    raw=tmp_path/'motion.bvh';raw.write_text('existing source bytes')
    artifact=tmp_path/'clip.npz';artifact.write_bytes(b'already converted output')
    row=dict(id='clip',source=str(raw),actor='actor_a',sampling_group='dance',anchor=True,evaluation_only=False)
    record=dict(row,source_sha256=sha(raw),output=str(artifact),output_sha256=sha(artifact),
                frames=100,grade='A_kinematic_candidate',status='converted',train_eligible=True,split='train')
    atomic(tmp_path/'records/clip.json',record)
    return tmp_path,row,artifact


def test_cached_evaluation_flag_is_persisted_and_training_rejects(cached):
    root,row,artifact=cached;before=artifact.read_bytes()
    result=_convert((dict(row,evaluation_only=True),root))
    assert result['evaluation_only'] is True and result['train_eligible'] is False
    assert result['split']=='evaluation'
    assert artifact.read_bytes()==before
    with pytest.raises(ValueError,match='External evaluation'):
        training_rows(load_records(root/'records'))
    assert json.loads((root/'records/clip.json').read_text())['evaluation_only'] is True


def test_cached_actor_category_anchor_changes_and_removed_metadata(cached):
    root,row,_=cached
    _convert((dict(row,custom_label='old'),root))
    changed=dict(row,actor='actor_b',sampling_group='dynamic');changed.pop('anchor')
    result=_convert((changed,root))
    assert (result['actor'],result['sampling_group'],result['anchor'])==('actor_b','dynamic',False)
    assert 'custom_label' not in result
    assert result['source_manifest_row']==source_row(changed)
    assert result['source_row_sha256']==row_sha(source_row(changed))


def test_catalog_rejects_stale_or_interrupted_conversion_and_excludes_removed(cached):
    root,row,_=cached
    _convert((row,root))
    changed=source_row(dict(row,evaluation_only=True))
    catalog=dict(status='complete',records={'clip':row_sha(changed)})
    atomic(root/'catalog.json',catalog)
    with pytest.raises(ValueError,match='Stale'):load_records(root/'records')
    _convert((changed,root))
    with pytest.raises(ValueError,match='External evaluation'):training_rows(load_records(root/'records'))
    atomic(root/'catalog.json',dict(catalog,status='converting'))
    with pytest.raises(ValueError,match='incomplete'):load_records(root/'records')
    atomic(root/'catalog.json',dict(status='complete',records={}))
    assert load_records(root/'records')==[]


@pytest.mark.parametrize('field,value',[('evaluation_only','false'),('anchor',1),('grade','A_kinematic_candidate'),('train_eligible',True)])
def test_manifest_cannot_spoof_metadata_types_or_conversion_evidence(cached,field,value):
    root,row,_=cached
    with pytest.raises(ValueError):_convert((dict(row,**{field:value}),root))


def test_changed_source_or_output_is_not_reused(cached):
    root,row,artifact=cached
    artifact.write_bytes(b'changed')
    with pytest.raises(ValueError,match='Changed output'):_convert((row,root))


def optimizer(lr):
    return SimpleNamespace(param_groups=[{'lr':lr}])


def arguments(**kwargs):
    return SimpleNamespace(**dict(dict(pi_lr=6e-5,max_hours=6.,freeze_pi_iters=0,reset_pi_schedule=False),**kwargs))


def legacy_checkpoint(lr=1.959957674e-5):
    return dict(iteration=12341,wall_time=4.5*3600,args=dict(pi_lr=6e-5,max_hours=5.),
                opt_pi=dict(param_groups=[dict(lr=lr)]))


def test_legacy_12341_first_rate_is_preserved_and_tail_does_not_increase():
    ck=legacy_checkpoint();saved=ck['opt_pi']['param_groups'][0]['lr'];opt=optimizer(saved)
    s=PolicyLRSchedule.create(arguments(),opt,ck)
    rates=[s.apply(opt,12341+i,t) for i,t in enumerate([0,1,600,1800,3600])]
    assert rates[0]==saved
    assert all(a>=b for a,b in zip(rates,rates[1:]))
    assert rates[-1]==pytest.approx(1.8e-5)


def test_new_schedule_serialized_resume_matches_uninterrupted_even_if_budget_extended():
    args=arguments(max_hours=1.,freeze_pi_iters=0)
    live_opt=optimizer(6e-5);live=PolicyLRSchedule.create(args,live_opt)
    live.apply(live_opt,100,900.)
    state=json.loads(json.dumps(live.state_dict()))
    saved_rate=live_opt.param_groups[0]['lr']
    ck=dict(iteration=101,wall_time=901.,args=vars(args),policy_lr_schedule=state)
    resumed_opt=optimizer(saved_rate)
    resumed=PolicyLRSchedule.create(arguments(max_hours=10.,pi_lr=1e-3,freeze_pi_iters=999),resumed_opt,ck)
    assert resumed.apply(resumed_opt,101,0.)==saved_rate
    for delta in [1.,100.,2700.,9000.]:
        assert resumed.apply(resumed_opt,102,delta)==live.apply(live_opt,102,900.+delta)


def test_freeze_window_is_not_restarted_on_resume():
    opt=optimizer(6e-5);args=arguments(max_hours=1.,freeze_pi_iters=2)
    s=PolicyLRSchedule.create(args,opt)
    assert s.apply(opt,0,0.)==0
    assert s.apply(opt,1,1.)==0
    ck=dict(iteration=2,wall_time=2.,args=vars(args),policy_lr_schedule=s.state_dict())
    resumed=PolicyLRSchedule.create(args,opt,ck)
    assert resumed.apply(opt,2,0.)>0


def test_lr_restart_requires_explicit_option():
    ck=legacy_checkpoint();opt=optimizer(ck['opt_pi']['param_groups'][0]['lr'])
    s=PolicyLRSchedule.create(arguments(reset_pi_schedule=True),opt,ck)
    assert s.apply(opt,12341,0.)==6e-5


def test_ambiguous_zero_legacy_lr_is_rejected():
    with pytest.raises(ValueError,match='Ambiguous legacy'):
        PolicyLRSchedule.create(arguments(),optimizer(0.),legacy_checkpoint(0.))


@pytest.fixture
def contract():
    return json.loads((Path(__file__).parents[1]/'configs/baseline_12341.json').read_text())


def identity(contract):
    return evaluation.history_identity(contract,{'gbtc':'ref_sha'},'height_diagnostic_v1','native',0)


@pytest.mark.parametrize('field,value',[
    ('compiled_model_sha256','different_physics'),('kp',[0.]*29),('action_scale',[.1]*29),
    ('default_q',[1.]*29),('control_dt',.01),('decimation',2),('mujoco_version','different'),
    ('motor_feedback_precision','float64'),('root_feedback_source','estimator'),
    ('term_height',.5),('future_control_field','must_be_checked')])
def test_history_rejects_changed_physics_or_any_control_field(tmp_path,contract,field,value):
    atomic(tmp_path/'identity.json',identity(contract));atomic(tmp_path/'best.json',{'preserve':'best'})
    before=(tmp_path/'best.json').read_bytes()
    with pytest.raises(ValueError,match='mismatch'):
        with evaluation.history_transaction(tmp_path,identity(dict(contract,**{field:value}))):
            pytest.fail('Incompatible evaluation entered history transaction')
    assert (tmp_path/'best.json').read_bytes()==before


def test_different_actor_is_allowed_under_identical_conditions(tmp_path,contract):
    atomic(tmp_path/'identity.json',identity(contract))
    changed=dict(contract,iteration=999,checkpoint='another.pt',checkpoint_sha256='another',policy_sha256='another')
    evaluation.validate_history(tmp_path,identity(changed))


def test_legacy_or_unidentified_history_is_not_silently_upgraded(tmp_path,contract):
    atomic(tmp_path/'best.json',{'preserve':True})
    with pytest.raises(ValueError,match='no verified'):evaluation.validate_history(tmp_path,identity(contract))
    atomic(tmp_path/'identity.json',dict(model_sha256=contract['model_sha256']))
    with pytest.raises(ValueError,match='legacy'):evaluation.validate_history(tmp_path,identity(contract))


def test_evaluate_rejects_before_rollout_or_best_update(tmp_path,contract,monkeypatch):
    ref=tmp_path/'reference.npz';ref.write_bytes(b'reference identity fixture')
    suite=tmp_path/'suite.json';atomic(suite,dict(references={'gbtc':dict(reference=str(ref),reference_sha256=sha(ref))}))
    history=tmp_path/'history';original=evaluation.history_identity(contract,{'gbtc':sha(ref)},'height_diagnostic_v1','native',0)
    atomic(history/'identity.json',original);atomic(history/'best.json',{'preserve':True})
    before=(history/'best.json').read_bytes();calls=[]
    def export_only(cmd,log,env,**kwargs):
        calls.append(cmd)
        assert 'dex_supermimic.deployment.build_bundle' in cmd,'Rollout started before identity validation'
        bundle=Path(cmd[cmd.index('--out')+1]);bundle.mkdir()
        (bundle/'model.mjb').write_bytes(b'changed compiled physics')
        atomic(bundle/'contract.json',dict(contract,compiled_model_sha256=sha(bundle/'model.mjb')))
    monkeypatch.setattr(evaluation,'run',export_only)
    args=argparse.Namespace(suite=str(suite),out=str(tmp_path/'out'),history=str(history),checkpoint='unused',
                            ros_python=None,max_steps=0,render=False)
    with pytest.raises(ValueError,match='mismatch'):evaluation.evaluate(args)
    assert len(calls)==1
    assert (history/'best.json').read_bytes()==before

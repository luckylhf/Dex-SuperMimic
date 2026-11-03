"""Load learned actor and world-model weights, with a zero-output correction head."""
from pathlib import Path
import hashlib,json,torch

def initialize_from_weights(wm,pi,pi_avg,source,log_dir):
    ck=torch.load(source,map_location=next(pi.parameters()).device,weights_only=False)
    wm.load_state_dict(ck['wm'])
    result=pi.load_state_dict(ck['pi'],strict=False)
    expected={k for k in pi.state_dict() if k.startswith('root_head.')}
    assert set(result.missing_keys)==expected and not result.unexpected_keys
    for name,value in ck['pi'].items():assert torch.equal(value.to(pi.state_dict()[name].device),pi.state_dict()[name]),name
    if pi.root_feedback:
        assert not torch.count_nonzero(pi.root_head[-1].weight) and not torch.count_nonzero(pi.root_head[-1].bias)
    if pi_avg is not None:
        pi_avg.module.load_state_dict(pi.state_dict());pi_avg.n_averaged.fill_(1)
    proof=dict(kind='weight initialization, not optimizer/critic resume',source=str(source),source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
               source_iteration=ck['iteration'],root_feedback=pi.root_feedback,all_inherited_actor_tensors_exact=True,new_keys=sorted(expected),
               correction_head_initial_output_zero=pi.root_feedback,optimizer_and_critic_rebuilt=True)
    (Path(log_dir)/'warm_start_proof.json').write_text(json.dumps(proof,indent=2))

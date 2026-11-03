"""Serializable wall-time policy schedule; resuming does not restart the cosine."""
import copy
import math


class PolicyLRSchedule:
    def __init__(self, state):
        self.state = copy.deepcopy(state)
        if state.get('version') != 1: raise ValueError('Unsupported policy LR schedule')
        self.offset = float(state['elapsed_seconds'])

    @classmethod
    def create(cls, args, optimizer, checkpoint=None):
        groups = optimizer.param_groups
        reset = getattr(args, 'reset_pi_schedule', False)
        saved = checkpoint.get('policy_lr_schedule') if checkpoint else None
        if saved and not reset:
            schedule = cls(saved)
            if len(saved['last_lrs']) != len(groups): raise ValueError('Policy optimizer group count changed')
            if any(g['lr'] != lr for g,lr in zip(groups,saved['last_lrs'])):
                raise ValueError('Optimizer LR disagrees with saved schedule')
            return schedule
        wall = float(checkpoint['wall_time']) if checkpoint else 0.
        start_it = int(checkpoint['iteration']) if checkpoint else 0
        if checkpoint and not reset:
            # Legacy checkpoints did not record their stage origin. Anchor the
            # first resumed update to the actual optimizer LR and recover the
            # remaining cosine phase from the old peak/floor and stop budget.
            old = checkpoint['args']
            peak = float(old['pi_lr'])
            initial = [float(g['lr']) for g in groups]
            if peak <= 0 or any(not math.isfinite(x) or x <= 0 or x > peak for x in initial):
                raise ValueError('Ambiguous legacy policy LR; use --reset_pi_schedule only for an intentional new schedule')
            duration = max(0., float(old['max_hours'])*3600-wall) if old.get('max_hours') is not None else 0.
            phases=[];floors=[]
            for rate in initial:
                floor=min(rate,peak*.3);floors.append(floor)
                phase=math.acos(max(-1.,min(1.,2*(rate-floor)/(peak-floor)-1)))/math.pi if peak>floor else 1.
                phases.append(phase)
            freeze_until=0
            origin='legacy_optimizer_anchor' if duration>0 else 'legacy_hold_without_remaining_budget'
        else:
            peak=float(args.pi_lr)
            if not math.isfinite(peak) or peak<=0: raise ValueError('pi_lr must be positive and finite')
            duration=max(1.,float(args.max_hours)*3600-wall) if args.max_hours is not None else 3600.
            initial=[peak]*len(groups);floors=[peak*.3]*len(groups);phases=[0.]*len(groups)
            freeze_until=start_it+args.freeze_pi_iters
            origin='explicit_reset' if checkpoint else 'new_schedule'
        return cls(dict(version=1,origin=origin,peak_lr=peak,initial_lrs=initial,floor_lrs=floors,
                        phase_starts=phases,duration_seconds=duration,elapsed_seconds=0.,
                        freeze_until_iteration=freeze_until,last_lrs=[float(g['lr']) for g in groups]))

    def apply(self, optimizer, iteration, elapsed_seconds):
        elapsed=max(0.,self.offset+float(elapsed_seconds))
        s=self.state
        if iteration<s['freeze_until_iteration']:
            rates=[0.]*len(s['initial_lrs'])
        elif elapsed==0. or s['duration_seconds']==0.:
            rates=list(s['initial_lrs'])
        else:
            progress=min(1.,elapsed/s['duration_seconds'])
            rates=[floor+(s['peak_lr']-floor)*.5*(1+math.cos(math.pi*(phase+(1-phase)*progress)))
                   for floor,phase in zip(s['floor_lrs'],s['phase_starts'])]
        if len(optimizer.param_groups)!=len(rates):raise ValueError('Policy optimizer group count changed')
        for group,rate in zip(optimizer.param_groups,rates):group['lr']=rate
        s.update(elapsed_seconds=elapsed,last_lrs=rates)
        return rates[0]

    def state_dict(self):
        return copy.deepcopy(self.state)

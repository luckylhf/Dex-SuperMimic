"""Projection onto bounded per-frame joint changes for offline pose refinement."""
import numpy as np
from scipy.sparse.linalg import lsmr

def project_velocity(q,step,lower,upper):
    """Alternating convex projections, vectorized over disjoint time edges.

    Each pair correction moves both endpoints toward their mean, so joint
    limits are preserved. This is a numerical continuity bound, not an
    actuator-speed specification. Returns a feasible joint trajectory.
    """
    out=np.clip(np.asarray(q).copy(),lower,upper)
    for _ in range(1200):
        for parity in (0,1):
            a=np.arange(parity,len(out)-1,2);b=a+1
            delta=out[b]-out[a];correction=(delta-np.clip(delta,-step,step))*.5
            out[a]+=correction;out[b]-=correction
        if np.max(np.maximum(abs(np.diff(out,axis=0))-step,0))<1e-8:break
    return out

def constrained_refine(q,fun,jac,lower,upper,step,iterations=8):
    """Projected Gauss-Newton keeps pose fitting in the continuity solve.

    A plain after-the-fact filter would discard the hand orientation goals.
    Here every accepted update lowers the SAME full pose+temporal objective
    while remaining inside the joint and time-step constraints.
    """
    shape=q.shape
    z=project_velocity(q,step,lower,upper).ravel();res=fun(z);cost=res@res
    used=0
    for k in range(iterations):
        J=jac(z);delta=lsmr(J,-res,damp=.01,maxiter=70,atol=1e-5,btol=1e-5)[0]
        delta*=min(1.,.25/max(np.max(abs(delta)),1e-12))
        improved=False
        for alpha in (1.,.5,.25,.125):
            proposal=project_velocity((z+alpha*delta).reshape(shape),step,lower,upper).ravel()
            rnew=fun(proposal);newcost=rnew@rnew
            if newcost<cost-1e-7:
                z,res,cost=proposal,rnew,newcost;improved=True;used=k+1;break
        if not improved:break
    return z.reshape(shape),{'iterations':used,'cost':float(cost),'max_step_deg':float(np.rad2deg(np.max(abs(np.diff(z.reshape(shape),axis=0)))))}

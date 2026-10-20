"""Independent spherical ray quadrature for monotonically upgoing SH legs.

Distances are degrees, depths and velocities km and km/s, times seconds.
ObsPy supplies the tabulated PREM material model, not these ray integrals.
Caching one vectorized radial quadrature per image depth avoids millions of
individual TauP calls. Rays beyond grazing incidence are explicitly absent.
"""
from functools import lru_cache
import numpy as np
from numpy.polynomial.legendre import leggauss
from obspy.taup import TauPyModel

RADIUS=6371.0
CMB=2891.0


@lru_cache(maxsize=1)
def prem_layers():
    return TauPyModel('prem').model.s_mod.v_mod.layers


def velocity(depth):
    """Linear interpolation within PREM layers, with its solid surface cap.

    TauP's prem.nd already replaces the ocean by the upper solid crust. Below
    the CMB extend mantle Vs solely to display post-ScS time, not core SH waves.
    """
    d=np.minimum(np.asarray(depth),CMB-1e-6)
    layers=prem_layers()
    i=np.searchsorted(layers['bot_depth'],d,side='right')
    layer=layers[i]
    f=(d-layer['top_depth'])/(layer['bot_depth']-layer['top_depth'])
    return layer['top_s_velocity']+f*(layer['bot_s_velocity']-layer['top_s_velocity'])


def leg_curves(target_depth, endpoint_depths, n_ray=1000, quadrature_order=16, spacing_km=15, constant_speed=None):
    """Return p, angle(p), time(p) for target -> each shallower endpoint.

    Split quadrature exactly at velocity jumps and endpoint depths. The p grid
    clusters near grazing incidence. A small terminal gap excludes the singular
    horizontal ray; no below-target turning path is admitted.
    """
    endpoints=np.asarray(endpoint_depths,dtype=float)
    breaks=np.unique(np.r_[np.arange(0,target_depth,spacing_km),
                            prem_layers()['top_depth'], endpoints, target_depth])
    breaks=breaks[(breaks>=0)&(breaks<=target_depth)]
    nodes,weights=leggauss(quadrature_order)
    low,high=breaks[:-1],breaks[1:]
    # r-r_target = u² removes the endpoint square-root singularity at grazing.
    u_low=np.sqrt(target_depth-high);u_high=np.sqrt(target_depth-low)
    u=((u_high-u_low)[:,None]*nodes/2+(u_high+u_low)[:,None]/2)
    depth=(target_depth-u*u).ravel()
    weight=((u_high-u_low)[:,None]*weights*u).ravel()
    r=RADIUS-depth
    v=velocity(depth) if constant_speed is None else np.full_like(depth,constant_speed)
    # All endpoints lie above the image domain. PREM r/v is minimized at the
    # deepest point in this domain; include that endpoint when bounding p.
    target_speed=float(velocity(target_depth)) if constant_speed is None else constant_speed
    pmax=min(np.min(r/v),(RADIUS-target_depth)/target_speed)
    u=np.linspace(0,0.995,n_ray)
    p=pmax*(1-(1-u)**3)
    q=np.sqrt(np.maximum(1-(p[:,None]*v/r)**2,1e-15))
    angle_terms=p[:,None]*v/(r*r*q)*weight
    time_terms=weight/(v*q)
    # Sum each radial interval before taking a cumulative integral from surface.
    angle=np.cumsum(angle_terms.reshape(n_ray,-1,quadrature_order).sum(axis=2),axis=1)
    travel=np.cumsum(time_terms.reshape(n_ray,-1,quadrature_order).sum(axis=2),axis=1)
    angle=np.column_stack([np.zeros(n_ray),angle]); travel=np.column_stack([np.zeros(n_ray),travel])
    result=[]
    for d in endpoints:
        j=np.searchsorted(breaks,d)
        result.append((np.rad2deg(angle[:,-1]-angle[:,j]),travel[:,-1]-travel[:,j]))
    return p,result


def make_tables(depths,endpoint_depths,distance_axis):
    tables=np.full((len(endpoint_depths),len(depths),len(distance_axis)),np.nan,dtype=np.float32)
    for k,z in enumerate(depths):
        _,curves=leg_curves(float(z),endpoint_depths)
        for i,(angle,travel) in enumerate(curves):
            tables[i,k]=np.interp(distance_axis,angle,travel,left=np.nan,right=np.nan)
    return tables


def reflection_time(depth, source_depth, distance):
    p,curves=leg_curves(depth,[source_depth,0])
    angle=curves[0][0]+curves[1][0]
    travel=curves[0][1]+curves[1][1]
    return float(np.interp(distance,angle,travel,left=np.nan,right=np.nan))

"""Spherical geometry in degrees; geocentric sphere of radius 6371 km."""
import numpy as np


def unit_vector(lat,lon):
    lat,lon=np.deg2rad(lat),np.deg2rad(lon)
    return np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])


def angular_distance(lat1,lon1,lat2,lon2):
    a,b,c,d=np.deg2rad([lat1,lon1,lat2,lon2]) if np.ndim(lat2)==0 else (
        np.deg2rad(lat1),np.deg2rad(lon1),np.deg2rad(lat2),np.deg2rad(lon2))
    h=np.sin((c-a)/2)**2+np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2
    return np.rad2deg(2*np.arcsin(np.sqrt(np.clip(h,0,1))))


def great_circle_point(lat1,lon1,lat2,lon2,fraction):
    a=unit_vector(lat1,lon1); b=unit_vector(lat2,lon2)
    angle=np.arccos(np.clip(a@b,-1,1))
    f=np.asarray(fraction)
    v=np.sin((1-f)*angle)[...,None]*a+np.sin(f*angle)[...,None]*b
    v/=np.linalg.norm(v,axis=-1)[...,None]
    return np.rad2deg(np.arcsin(v[...,2])),np.rad2deg(np.arctan2(v[...,1],v[...,0]))

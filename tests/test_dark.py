import sys, math, numpy as np
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..')); import pyoccult_pick as P
def v(ra,dec):
    ra,dec=math.radians(ra),math.radians(dec); return np.array([math.cos(dec)*math.cos(ra),math.cos(dec)*math.sin(ra),math.sin(dec)])
sun=v(0,0)                                    # equinox Sun
print("sun-down fraction (lat 40.95, -6 deg):", P.dark_fraction(sun,v(180,90-0.0001) if False else v(0,89.9),40.954,-90,-6,n=2400))
f_conj=P.dark_fraction(sun,v(0,0),40.954,10,-6,n=2400)       # asteroid at the Sun: never up in dark
f_opp =P.dark_fraction(sun,v(180,0),40.954,10,-6,n=2400)     # opposition
f_quad=P.dark_fraction(sun,v(90,0),40.954,10,-6,n=2400)      # east quadrature (evening)
print("conj",round(float(f_conj),3),"opp",round(float(f_opp),3),"quad",round(float(f_quad),3))
assert f_conj==0 and 0.30<f_opp<0.45 and 0<f_quad<f_opp
# analytic check of the equinox dark fraction: sun alt < -6 when cos h < (sin(-6)-0)/(cos(phi)) -> fraction = acos(.)/pi...
phi=math.radians(40.954); frac=math.acos(math.sin(math.radians(-6))/-1/ math.cos(phi) *-1)  # placeholder, recomputed below
c=(math.sin(math.radians(-6)))/math.cos(phi); analytic=(math.pi-math.acos(-c)) /math.pi if False else (1-math.acos(c)/math.pi)
# sun alt<-6 <=> cos(h) < c with h in [0,2pi): fraction = (2pi-2*acos(c))/2pi
analytic=(2*math.pi-2*math.acos(c))/(2*math.pi)
got=float(P.dark_fraction(sun,v(0,89.9),40.954,-90,-6,n=24000)); print("night fraction numeric",round(got,4),"analytic",round(analytic,4)); assert abs(got-analytic)<2e-3
print("dark OK")

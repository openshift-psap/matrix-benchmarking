#! /usr/bin/python3

import plotly.graph_objects as go
import numpy as np
from collections import defaultdict
import re
import sympy
import itertools

EQUATIONS = """
# display=webgl-wipeout
gpu render = framerate * 0.45 + 25.1 | resolution=0.92
gpu render = framerate * 0.47 + 48.3 | resolution=2.07

gpu render = resolution * 27.06 + 12.5 | framerate=30.00
gpu render = resolution * 27.22 + 16.6 | framerate=40.00
"""

_EQUATIONS = """
# display=img-lady-1920
gpu render = resolution * 5.16 + 6.5 | framerate=30.00
gpu render = resolution * 6.99 + 8.5 | framerate=40.00

gpu render = framerate * 0.40 + 0.01 | resolution=0.92
gpu render = framerate * 0.57 + 0.4 | resolution=2.07
"""

LENGTH = 10
EQ_RE = re.compile(r"(?P<z_var>.*) = (?P<x_var>.*) \* (?P<x_coeff>.*) \+ (?P<x_origin>.*) \| (?P<params>.*)")

title = None
data = []
z_title = None
max_params = defaultdict(float)
equations_settings = []

for equa in EQUATIONS.split("\n"):
    m = re.match(EQ_RE, equa)
    if not m:
        if equa.startswith("#"):
            print(equa)
            title = equa
        elif equa:
            print("Invalid equation:", equa)
        continue

    z_var, x_var, x_coeff, x_origin, params = m.groupdict().values()
    x_coeff = float(x_coeff)
    x_origin = float(x_origin)

    if "|" in params:
        print("Too many parameters ...")
        exit(1)
    if z_title is None:
        z_title = z_var
    elif z_var != z_title:
        print("Found different z params ... {z_title} and {z_var}")
        exit(1)

    y_var, y_val = params.split("=")
    y_val = float(y_val)
    max_params[y_var] = max(max_params[y_var], y_val)

    equations_settings.append([equa, x_var, x_coeff, x_origin, y_var, y_val])

x_title, y_title = max_params.keys()

for _, x_var, x_coeff, x_origin, y_var, y_val in equations_settings:
    series = np.linspace(0, max_params[x_var] * 1.1, LENGTH)
    fixed = [y_val] * LENGTH
    if list(max_params.keys()).index(x_var) == 0:
        x = series ; y = fixed
    else:
        y = series ; x = fixed
    z = series * x_coeff + x_origin
    name = f"{x_var} | {y_var}={y_val}"
    data += [go.Scatter3d(x=x, y=y, z=z, mode='lines', name=name)]


# ---

f, r, gpu = sympy.symbols("f r gpu")
aFR, aR, aF, b = sympy.symbols("aFR aR aF b")

ns = {str(s):s for s in [f, r, gpu, aFR, aR, aF, b]}
main_eq = aFR*f*r + aR*r + aF*f

syst = []
for eq in equations_settings:
    equa, x_var, x_coeff, x_origin, y_var, y_val = eq

    local_eq = sympy.simplify(f"{x_var[0]} * {x_coeff} + {x_origin}", ns=ns)

    for x_val in 0, max_params[x_var]:
        main_eq_at_xy = main_eq.subs(y_var[0], y_val).subs(x_var[0], x_val)
        local_eq_at_x = local_eq.subs(x_var[0], x_val)
        syst.append(sympy.Eq(local_eq_at_x, main_eq_at_xy))
        print(f"> {syst[-1].lhs:.2f} = {syst[-1].rhs}")

print("---")

for idx, (s1, s2, s3) in enumerate(itertools.combinations(syst, 3)):
    solutions = sympy.solve([s1, s2, s3])
    if not solutions:
        #print(f"[{s1}, {s2}, {s3}] --> no solution")
        print(f"#{idx} no solution")
        continue

    sol_expr = main_eq.subs(solutions)
    sol_str = f"#{idx} {sol_expr}"
    print(sol_str)

    def fxy(_f, _r):
        v = float(sol_expr.subs({r:_r, f:_f}))
        if v < 0: v = 0
        if v > 100: v = 100
        return v

    estim_x = np.linspace(0.0, max_params[x_title], LENGTH) # fps
    estim_y = np.linspace(0.0, max_params[y_title], LENGTH) # res
    estim_z = [[100]*LENGTH for _ in range(LENGTH)]

    for i, _x in enumerate(estim_x):
        for j, _y in enumerate(estim_y):
            estim_z[j][i] = fxy(**{"_"+x_title[0]: _x, "_"+y_title[0]: _y})


    data += [go.Surface(x=estim_x, y=estim_y, z=estim_z, hoverlabel={'namelength':-1},
                        legendgroup=sol_str, name=f"Solution #{idx}", showscale=False),
             go.Scatter3d(x=[1], y=[1], z=[1], mode='lines', name=sol_str, legendgroup=sol_str)
    ]

#

# ---

fig = go.Figure(data=data)

fig.update_layout(margin=dict(l=0, r=0, b=0, t=0),
                  title={
                      'text': f"{z_var} for {title}",
                      'y':0.9, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'})
fig.update_layout(xaxis_title="framerate", yaxis_title="CPU")
fig.update_layout(scene = dict(
                    xaxis_title=x_title,
                    yaxis_title=y_title,
                    zaxis_title=z_title),
                    margin=dict(r=20, b=10, l=10, t=10))
fig.show()

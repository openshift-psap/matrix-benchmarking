#! /usr/bin/python3

import plotly.graph_objects as go
import numpy as np

data = []

LENGTH = 50
FPS = np.linspace(0, 50, LENGTH)
RES = np.linspace(0, 2.5, LENGTH)

# FPS | res=720p
x = FPS
res = [0.92] * LENGTH
gpu = x * 0.45 + 25
data += [go.Scatter3d(x=x, y=res, z=gpu, mode='lines', name="FPS | res=720p")]

# FPS | res=1080p
x = FPS
res = [2.07] * LENGTH
gpu = x * 0.45 + 48
data += [go.Scatter3d(x=x, y=res, z=gpu, mode='lines', name="FPS | res=1080p")]

# RES | fps=30
y = RES
gpu = y * 27 + 12
fps = [30] * LENGTH
data += [go.Scatter3d(x=fps, y=y, z=gpu, mode='lines', name="RES | fps=30")]

# RES | fps=40
y = RES
gpu = y * 27 + 16
fps = [40] * LENGTH
data += [go.Scatter3d(x=fps, y=y, z=gpu, mode='lines', name="RES | fps=40")]

# ---

# RES | fps=0

y = RES
gpu = y * 20 + 6.6
fps = [0] * LENGTH
data += [go.Scatter3d(x=fps, y=y, z=gpu, mode='lines', name="RES | fps=0")]

# RES | fps=50

y = RES
gpu = y * 20 + 29.1
fps = [50] * LENGTH
data += [go.Scatter3d(x=fps, y=y, z=gpu, mode='lines', name="RES | fps=50")]


# FPS | res=0
x = FPS
gpu = x * 2/5 + 6.6
res = [0] * LENGTH
#data += [go.Scatter3d(x=x, y=res, z=gpu, mode='lines', name="FPS | res=0")]

# RES | fps=0
res = [0] * LENGTH
x = FPS
gpu = x * 0.46 + 6.6
data += [go.Scatter3d(x=x, y=res, z=gpu, mode='lines', name="FPS | res=0")]

# FPS | res=2.5
res = [2.5] * LENGTH
x = FPS
gpu = x * 0.46 + 56.6
data += [go.Scatter3d(x=x, y=res, z=gpu, mode='lines', name="FPS | res=2.5")]

# ---

estim_x = np.linspace(0.0, 50, LENGTH)
estim_y = np.linspace(0.0, 2.5, LENGTH)
estim_z = [[100]*LENGTH for _ in range(LENGTH)]

for i, _x in enumerate(estim_x):
    for j, _y in enumerate(estim_y):
        estim_z[j][i] =  _y*20 + _x*0.46 + 6.6

data += [go.Surface(x=estim_x, y=estim_y, z=estim_z, name="Estim")]

# ---

fig = go.Figure(data=data)

fig.update_layout(margin=dict(l=0, r=0, b=0, t=0))
fig.update_layout(xaxis_title="framerate", yaxis_title="GPU")
fig.update_layout(scene = dict(
                    xaxis_title='framerate',
                    zaxis_title='GPU',
                    yaxis_title='resolution'),
                    width=1000, height=900,
                    margin=dict(r=20, b=10, l=10, t=10))


fig.show()
exit()

import dash
import dash_core_components as dcc
import dash_html_components as html

app = dash.Dash()
app.layout = html.Div([
    dcc.Graph(figure=fig)
])

app.run_server(debug=True)

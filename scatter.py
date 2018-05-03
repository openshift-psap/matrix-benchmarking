#!/usr/bin/python3
import matplotlib.pyplot as plt
import numpy as np
import pandas as pa

# read data
data = pa.read_csv('out.csv')
# consider only frames data
data = data.loc[~np.isnan(data['capture'])]
# filter 2 columns
data = data.filter(items=['bytes', 'decode'])
# remove initial rows, can be inaccurate
data = data[10:-3]

plt.scatter(data['bytes'], data['decode'], alpha=0.1)
plt.xlabel("Frame size (bytes)")
plt.ylabel("Time to decode (ms)")
plt.show()

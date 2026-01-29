import diplotocus as dpl
import numpy as np
import matplotlib.pyplot as plt

fig,ax = plt.subplots(figsize=(12,5))
ax.set_axis_off()

x = np.linspace(0,10,100)
y = np.cos(x)

a = dpl.scatter(x=x,y=y)

x = np.linspace(0,10,100)
y = np.sin(x)
x = np.cos(x)*2 + 5

b = dpl.plot(x=x,y=y,color='C1')

seq = dpl.Sequence(fig=fig,transparent=True,white=True)

GUI = dpl.GUI.GUI(seq=seq,plot_objects=
    [
        {
            'name':'scatter',
            'object':a
        },
        {
            'name':'plot',
            'object':b
        },
    ]
)
GUI.open()
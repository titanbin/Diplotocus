import numpy as np
import subprocess,os,shlex,pickle
import matplotlib.pyplot as plt
import matplotlib
from copy import deepcopy
matplotlib.use("Agg")
import shutil
try:
    from IPython.display import HTML, display
except:
    pass

from .easings import *
from .animations import *

def in_notebook():
    try:
        from IPython import get_ipython
        from IPython.display import HTML, display
        shell = get_ipython().__class__.__name__
        return shell == "ZMQInteractiveShell"
    except Exception:
        return False

if in_notebook():
    from tqdm.notebook import tqdm
else:
    from tqdm import tqdm

def status_message(start_msg, end_msg):
    if in_notebook():
        from IPython.display import display, update_display, Markdown
        display_id = display(Markdown(start_msg), display_id=True)
        def update():
            update_display(Markdown(end_msg), display_id=display_id.display_id)
        return update
    else:
        print(start_msg, end="\r", flush=True)
        def update():
            print(end_msg + " " * max(0, len(start_msg) - len(end_msg)))
        return update

#----------------------------------------------
# SEQUENCE CLASS
#----------------------------------------------

def load_project(path):
    seq = pickle.load(open(path, 'rb'))
    animations = seq.animations
    seq.x = 0
    seq.clean_all()
    return seq,animations

class Sequence:
    def __init__(self,name='Unnamed',fig=None,quiet=False,dpi=200,transparent=False,white=False,noaxis=False,easing=easeLinear()):
        if fig is None:
            fig,_ = plt.subplots()
        self.fig = fig
        self.ax = self.fig.get_axes()
        if len(self.ax) == 1:
            self.ax = self.ax[0]
        else:
            self.ax = np.array(self.ax)
        if isinstance(self.ax,np.ndarray):
            if isinstance(self.ax[0],np.ndarray):
                self.main_axis = self.ax[0,0]
            else:
                self.main_axis = self.ax[0]
        else:
            self.main_axis = self.ax
        self.name = name
        self.quiet = quiet
        self.dpi = dpi
        self.easing = easing
        self.x = 0
        self.sequence_str = ''
        self.transparent = transparent
        self.animations = []
        if in_notebook() == False:
            namespace = sys._getframe(1).f_globals['__file__']
            self.full_path = '/'.join(namespace.split('/')[:-1])
        if white:
            self.set_white()
        if noaxis:
            self.main_axis.set_axis_off()

    def set_white(self):
        if isinstance(self.ax,np.ndarray) == False:
            axes = (self.ax,)
        else:
            axes = self.ax.flatten()
        for axis in axes:
            axis.spines['bottom'].set_color('white')
            axis.spines['top'].set_color('white')
            axis.spines['left'].set_color('white')
            axis.spines['right'].set_color('white')
            axis.xaxis.label.set_color('white')
            axis.yaxis.label.set_color('white')
            axis.tick_params(axis='both',colors='white')

    def clean_all(self):
        axes = np.ravel(self.ax)
        for axis in axes:
            for line in axis.lines:
                line = np.ravel(line)
                for l in line:
                    if l.get_animated():
                        l.remove()
            for coll in axis.collections:
                coll = np.ravel(coll)
                for c in coll:
                    if c.get_animated():
                        c.remove()
            for patch in axis.patches:
                patch = np.ravel(patch)
                for p in patch:
                    if p.get_animated():
                        p.remove()

    def plot(self,animations,x=0,easing=None,debug=False):
        if isinstance(animations,Animation):
            animations = (animations,)

        for animation in animations:
            if animation.obj is not None and ((animation.x_min <= x < animation.x_max) or (x >= animation.x_max and animation.persistent == False)):
                objects = np.ravel(animation.obj)
                for obj in objects:
                    try:
                        obj.remove()
                    except:
                        pass
            
            animation.initialize(self)
            #only plot if within an anim or if last one is persistent
            last_anim = None
            closest_dist = np.inf
            for anim in animation.anims:
                anim_x_max = anim['duration']+anim['delay']
                if anim_x_max > x:
                    continue
                dist = x - anim_x_max
                if dist < closest_dist:
                    closest_dist = dist
                    last_anim = anim
            is_within_anim = False
            if last_anim is not None:
                is_within_anim = last_anim['persistent'] == True
            if is_within_anim == False:
                for anim in animation.anims:
                    anim_x_min = anim['delay']
                    anim_x_max = anim['duration']+anim['delay']
                    if anim_x_min <= x < anim_x_max:
                        is_within_anim = True
                        break
            if is_within_anim:
                animation.apply(x)
        prev_x = self.x
        self.x = x
        self.save_plot(debug)
        for animation in animations:
            animation.clean(x,clear_anims=False)
        self.x = prev_x

    def animate(self,animations,easing=None,debug=False):
        if isinstance(animations,Animation):
            animations = (animations,)
        self.animations = deepcopy(np.array(animations))
        
        x_max = 0
        for animation in animations:
            animation.initialize(self)

            if animation.x_max > x_max:
                x_max = animation.x_max
        
        loop = range(x_max)
        if not self.quiet:
            loop = tqdm(loop)

        for x in loop:
            self.plot(animations=animations,x=x,easing=easing,debug=debug)
        self.x = x_max

    def wait(self,duration):
        old_x = self.x
        for i in range(duration):
            self.sequence_str += 'file \'' + self.name + '_{}.png\'\n'.format(old_x - 1)
            self.sequence_str += 'duration {}\n'.format(1/30)
            self.x += 1

    def save_plot(self,debug):
        if debug is False:
            if os.path.isdir(self.name) == False:
                os.makedirs(self.name)
            fn = self.name + '/' + self.name +  '_{}.png'.format(self.x)
            self.fig.savefig(fn,dpi=self.dpi,transparent=self.transparent)
            
            self.sequence_str += 'file \'' + self.name + '_{}.png\'\n'.format(self.x)
            self.sequence_str += 'duration {}\n'.format(1/30)
        self.x += 1
    
    def save_video(self,path=None,speed=1,ffmpeg_path='ffmpeg',multialpha=False,prerendered=False,clean=True):
        if self.x == 0:
            raise UserWarning('No rendered frames, run animate with animations to generate frames !')
        if path is None:
            if self.transparent:
                path = self.name + '.mov'
            else:
                path = self.name + '.mp4'
        video_fn = path
        is_gif = video_fn.lower().endswith('.gif')
        if not self.quiet:
            update = status_message("Rendering video...", "Saved video " + video_fn)
        if not prerendered:
            self.sequence_str = ''
            for i in range(self.x):
                self.sequence_str += 'file \'' + self.name + '_{}.png\'\n'.format(i)
                self.sequence_str += 'duration {}\n'.format(1/30/speed)
            self.sequence_str += 'file \'' + self.name + '_{}.png\'\n'.format(i)
            self.sequence_str += 'duration {}\n'.format(1/30/speed)
            with open(self.name + '/' + self.name + '.txt','w+') as f:
                f.write(self.sequence_str)
        sequence_fn = self.name + '/' + self.name  + '.txt'

        if '.mov' in video_fn:
            if multialpha:
                command = ffmpeg_path + ' -f concat -safe 0 -i {} -y -vf premultiply=inplace=1 -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le -hide_banner -loglevel error {}'.format(sequence_fn,video_fn)
            else:
                command = ffmpeg_path + ' -f concat -safe 0 -i {} -y -c:v prores -pix_fmt yuva444p10le -hide_banner -loglevel error {}'.format(sequence_fn,video_fn)
        elif is_gif:
            command = ffmpeg_path + ' -f concat -safe 0 -i {} -y -lavfi "split[s0][s1];[s0]palettegen=reserve_transparent=1:stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a:alpha_threshold=128" -gifflags -offsetting -loop 0 -hide_banner -loglevel error {}'.format(sequence_fn,video_fn)
        else:
            command = ffmpeg_path + ' -f concat -safe 0 -i {} -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart -hide_banner -loglevel error -y {}'.format(sequence_fn,video_fn)
        subprocess.run(shlex.split(command))
        if clean:
            shutil.rmtree(self.name)
        plt.close()
        if not self.quiet:
            update()
        if is_gif:
            return display(HTML('<img src="{}" style="max-width:640px;height:auto;" />'.format(video_fn)))
        return display(HTML("""
            <video width="640" height="360" autoplay loop muted playsinline>
            <source src="{}" type="video/mp4">
            </video>
        """.format(video_fn)))
    
    def save_project(self,path):
        with open(path, 'wb') as f:
            pickle.dump(self, f)
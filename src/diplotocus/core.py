import numpy as np
import subprocess,os,shlex,pickle
import matplotlib.pyplot as plt
import matplotlib
import warnings
from copy import deepcopy
matplotlib.use("Agg")
import shutil
try:
    has_ipython = True
    from IPython.display import HTML, display
except:
    has_ipython = False
    pass

from .easings import *
from .animations import *

if shutil.which("ffmpeg") is None:
    warnings.warn("FFmpeg is required to render videos, but is not installed. Please install it system-wide.")

def in_notebook():
    try:
        from IPython import get_ipython
        from IPython.display import HTML, display
        shell = get_ipython().__class__.__name__
        return shell == "ZMQInteractiveShell"
    except Exception:
        return False

if in_notebook():
    try:
        from tqdm.notebook import tqdm
        has_tqdm = True
    except:
        has_tqdm = False
else:
    try:
        from tqdm import tqdm
        has_tqdm = True
    except:
        has_tqdm = False

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
# TIMELINE CLASS
#----------------------------------------------

def load_project(path):
    """Load a project.

    Parameters
    ----------
    path : str
        the path to the project file.

    Returns
    ----------
    (Timeline,list of plot objects)
    """
    tl = pickle.load(open(path, 'rb'))
    plot_objects = tl.plot_objects
    tl.x = 0
    tl.clean_all()
    return tl,plot_objects

class Timeline:
    """Create and manage an animation timeline.

    Parameters
    ----------
    name : str
        the name used for the rendered images folder.
    fig : Figure | None
        an existing Figure to plot on. If None, a new Figure will be created.
    quiet : bool
        if True, any message will not be printed, and no progress bar will be shown.
    dpi : int
        The DPI of the rendered images (higher = better resolution/slower render).
    transparent : bool
        if True, the background color of the Figure and axes will be transparent. Can be used to render a transparent video (only compatible with a .mov video file).
    axis_color : str
        if True, changes the color of the axes, ticks and labels to the specified color.
    noaxis : bool
        if True, hides the axis lines, ticks and labels.
    easing : easing
        a global easing to be used if no other easing is specified on an animation.
    xlim : tuple | None
        if fig is None, sets the X limits of the created axis.
    ylim : tuple | None
        if fig is None, sets the Y limits of the created axis.
    """
    def __init__(self,
                 name='Unnamed',
                 fig=None,
                 quiet=False,
                 dpi=200,
                 transparent=False,
                 axis_color='k',
                 noaxis=False,
                 easing=easeLinear(),
                 xlim=None,
                 ylim=None,
                 figsize=None
        ):
        if fig is None:
            if figsize is not None:
                fig,_ = plt.subplots(figsize=figsize)    
            else:
                fig,_ = plt.subplots()
        self.fig = fig
        self.ax = self.fig.get_axes()
        if len(self.ax) == 1:
            self.ax = self.ax[0]
        else:
            self.ax = np.array(self.ax)
        if isinstance(self.ax,np.ndarray):
            if isinstance(self.ax[0],np.ndarray):
                self.set_main_axis(self.ax[0,0])
            else:
                self.set_main_axis(self.ax[0])
        else:
            self.set_main_axis(self.ax)
        if xlim is not None:
            self.main_axis.set_xlim(*xlim)
        if ylim is not None:
            self.main_axis.set_ylim(*ylim)
        self.name = name
        self.quiet = quiet
        self.dpi = dpi
        self.easing = easing
        self.x = 0
        self.timeline_str = ''
        self.transparent = transparent
        self.plot_objects = []
        if in_notebook() == False:
            namespace = sys._getframe(1).f_globals['__file__']
            self.full_path = '/'.join(namespace.split('/')[:-1])
        if axis_color != 'k':
            self.set_axis_color(axis_color)
        if noaxis:
            self.main_axis.set_axis_off()

    def set_main_axis(self,ax):
        """Set the default axis to plot objects on

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            Axis to set as default
        """
        self.main_axis = ax

    def set_axis_color(self,color):
        """Set the color of axes

        Parameters
        ----------
        color : color or array-like, optional
            The color to set the axes
        """
        if isinstance(self.ax,np.ndarray) == False:
            axes = (self.ax,)
        else:
            axes = self.ax.flatten()
        for axis in axes:
            axis.spines['bottom'].set_color(color)
            axis.spines['top'].set_color(color)
            axis.spines['left'].set_color(color)
            axis.spines['right'].set_color(color)
            axis.xaxis.label.set_color(color)
            axis.yaxis.label.set_color(color)
            axis.tick_params(axis='both',colors=color)

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

    def plot(self,plot_objects,x=0,easing=None,debug=False):
        if isinstance(plot_objects,plotObject):
            plot_objects = (plot_objects,)

        for plot_object in plot_objects:
            if plot_object.obj is not None and ((plot_object.x_min <= x < plot_object.x_max) or (x >= plot_object.x_max and plot_object.persistent == False)):
                objects = np.ravel(plot_object.obj)
                for obj in objects:
                    try:
                        obj.remove()
                    except:
                        pass
            
            plot_object.initialize(self)
            #only plot if within an anim or if last one is persistent
            last_anim = None
            closest_dist = np.inf
            for anim in plot_object.anims:
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
                for anim in plot_object.anims:
                    anim_x_min = anim['delay']
                    anim_x_max = anim['duration']+anim['delay']
                    if anim_x_min <= x < anim_x_max:
                        is_within_anim = True
                        break
            if is_within_anim:
                plot_object.apply(x,easing)
        prev_x = self.x
        self.x = x
        self.save_plot(debug)
        for plot_object in plot_objects:
            plot_object.clean(x,clear_anims=False)
        self.x = prev_x

    def animate(self,plot_objects,easing=None,debug=False):
        """Render one or more plot objects into the timeline.

        Parameters
        ----------
        plot_objects : plotObject or sequence of plotObject
            a single plot object (e.g. `scatter`, `plot`, `hist`...) or a list of plot objects.
        easing : easing
            an easing override used while rendering.
        debug : bool
            if True, skip writing frame images to disk.
        """
        if isinstance(plot_objects,plotObject):
            plot_objects = (plot_objects,)
        self.animations = deepcopy(np.array(plot_objects))
        
        x_max = 0
        for animation in plot_objects:
            for anim in animation.anims:
                if anim['played'] == False:
                    anim['delay'] += self.x
            animation.initialize(self)

            if animation.x_max > x_max:
                x_max = animation.x_max
        
        loop = range(self.x,x_max)
        if not self.quiet and has_tqdm:
            loop = tqdm(loop)

        for x in loop:
            self.plot(plot_objects=plot_objects,x=x,easing=easing,debug=debug)
        for animation in plot_objects:
            for anim in animation.anims:
                anim['played'] = True
        self.x = x_max

    def wait(self,duration):
        """Pause the animation for a number of frames.

        Parameters
        ----------
        duration : int
            the number of frames to pause the animation for.
        """
        if self.x == 0:
            raise UserWarning('No rendered frames, run animate with animations to generate frames !')

        last_frame = self.x - 1
        source_png = self.name + '/' + self.name + '_{}.png'.format(last_frame)
        for _ in range(duration):
            target_png = self.name + '/' + self.name + '_{}.png'.format(self.x)
            shutil.copyfile(source_png, target_png)
            self.timeline_str += 'file \' ' + self.name + '_{}.png\'\n'.format(self.x)
            self.timeline_str += 'duration {}\n'.format(1/30)
            self.x += 1

    def save_plot(self,debug):
        if debug is False:
            if os.path.isdir(self.name) == False:
                os.makedirs(self.name)
            fn = self.name + '/' + self.name +  '_{}.png'.format(self.x)
            self.fig.savefig(fn,dpi=self.dpi,transparent=self.transparent)
            
            self.timeline_str += 'file \'' + self.name + '_{}.png\'\n'.format(self.x)
            self.timeline_str += 'duration {}\n'.format(1/30)
        self.x += 1
    
    def save_video(self,path=None,speed=1,ffmpeg_path='ffmpeg',multialpha=False,prerendered=False,clean=True):
        """Render the current timeline to a video file.

        Parameters
        ----------
        path : str | None
            the path to save the video file to.
        speed : float
            by default, animations are rendered at 30fps (frames per second). You can change this by setting the speed. For 60fps videos, choose speed=2.
        ffmpeg_path : str
             if ffmpeg is not recognised as is, you can set the path to the ffmpeg executable through this parameter.
        multialpha : bool
            when rendering to a transparent .mov video, if you have semi-transparent frames, can be used to get better results.
        prerendered : bool
            if save_video() was already called and clean was set to False, image files and the text list file associated still exist. If you want to rerender the video, without having to rerender all the frames, you can set prerendered to true, which will only run the ffmpeg command.
        clean : bool
            if True, image files and the text list file associated are deleted after the video has been rendered.
        """
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
            self.timeline_str = ''
            for i in range(self.x):
                self.timeline_str += 'file \'' + self.name + '_{}.png\'\n'.format(i)
                self.timeline_str += 'duration {}\n'.format(1/30/speed)
            self.timeline_str += 'file \'' + self.name + '_{}.png\'\n'.format(i)
            self.timeline_str += 'duration {}\n'.format(1/30/speed)
            with open(self.name + '/' + self.name + '.txt','w+') as f:
                f.write(self.timeline_str)
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
        
        rand_id = np.random.randint(0,10_000)
        if has_ipython:
            if is_gif:
                return display(HTML('<img src="{}?randId={}" style="max-width:640px;height:auto;" />'.format(video_fn,rand_id)))
            return display(HTML("""
                <video width="640" height="360" autoplay loop muted playsinline>
                <source src="{}?randId={}" type="video/mp4">
                </video>
            """.format(video_fn,rand_id)))
    
    def save_project(self,path):
        """Save the current Timeline and associated plot objects to a project file.

        Parameters
        ----------
        path : str
            The path to save the project file to.
        """
        with open(path, 'wb') as f:
            pickle.dump(self, f)
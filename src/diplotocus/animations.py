import numpy as np
import numbers,inspect
import matplotlib as mpl
import matplotlib.pyplot as plt
from svgpath2mpl import parse_path
from matplotlib import transforms
from matplotlib.textpath import TextPath
from matplotlib.patches import PathPatch
from matplotlib.font_manager import FontProperties

from . import easings

def dealias(mpl_obj,kwargs):
    if mpl_obj is None:
        return kwargs
    for alias in mpl_obj._alias_map:
        has_main_alias = alias in kwargs
        for other_alias in mpl_obj._alias_map[alias]:
            if other_alias in kwargs:
                if has_main_alias:
                    raise TypeError('Got both \'{}\' and \'{}\', which are aliases of one another'.format(alias,other_alias))
                else:
                    has_main_alias = True
                    kwargs[alias] = kwargs[other_alias]
                    kwargs.pop(other_alias)

    return kwargs

def to_np_array(obj):
    obj = np.array(obj)
    if obj.ndim == 0:
        obj = np.ravel(obj)
    return obj

class plotObject:
    """
    A parent plotObject object for all plotting objects.

    Parameters
    ----------
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on
    """
    def __init__(self,easing=None,axis=None,**kwargs):
        self.anims = []
        self.tl = None
        self.set_easing(easing)
        self.set_axis(axis)
        self.animate_easing = None
        self.obj = None
        self.base_color = None
        self.tween_properties = []
        self.x_min = 0
        self.x_max = 0
        self.tween_starts = []
        self.tween_ends = []
        self.transforms = []
        self.x = None
        self.y = None
        self.persistent = False
        self.T = transforms.Affine2D()
        if not hasattr(self, 'mpl_obj_type'):
            self.mpl_obj_type = None
        if not hasattr(self, 'mpl_plot_type'):
            self.mpl_plot_type = None
        self.alias_map = self.get_alias_map()
        self.possible_kwargs = self.get_possible_kwargs()

        kwargs = self.clean_kwargs(kwargs)
        kwargs['animated'] = True
        self.kwargs = kwargs
        self.kwargs = dealias(self.mpl_obj_type,self.kwargs)
        if 'alpha' not in self.kwargs:
            self.kwargs['alpha'] = 1

    def function(self):
        pass

    def init(self):
        pass

    def get_alias_map(self):
        if self.mpl_obj_type is None:
            return None
        alias_map = self.mpl_obj_type._alias_map
        if self.mpl_plot_type == plt.plot and False:
            alias_map['color'] = ['c']
        return alias_map

    def get_possible_kwargs(self):
        if self.mpl_obj_type is None or self.mpl_plot_type is None:
            return {}
        sig = inspect.signature(self.mpl_obj_type)
        kwargs = [
            param.name for param in sig.parameters.values() if
            (param.kind == param.KEYWORD_ONLY or param.kind == param.VAR_KEYWORD or param.default != param.empty)
            and param.name != 'kwargs']
        
        sig = inspect.signature(self.mpl_plot_type)
        kwargs += [
            param.name for param in sig.parameters.values() if
            (param.kind == param.KEYWORD_ONLY or param.kind == param.VAR_KEYWORD or param.default != param.empty)
            and param.name != 'kwargs']
        return kwargs
    
    def get_main_alias(self,properties):
        if self.mpl_obj_type is None:
            return properties
        is_iterable = isinstance(properties,(list,np.ndarray,tuple))
        properties = to_np_array(properties).astype(np.object_)
        for i,property in enumerate(properties):
            if property not in self.alias_map:
                for alias in self.alias_map:
                    if property in self.alias_map[alias]:
                        properties[i] = alias
        if is_iterable:
            return properties
        return properties[0]

    def set_axis(self,axis):
        self.axis = axis
        if self.axis is None and self.tl is not None:
            self.set_axis(self.tl.main_axis)
        return self

    def set_easing(self,easing):
        self.easing = easing
        return self

    def apply(self,x,animate_easing):
        self.animate_easing = animate_easing
        if x < self.x_min:
            return
        if x >= self.x_max and self.persistent == False:
            self.clean(self.x_max-2,clear_anims=False)
            return
        self.T = transforms.Affine2D()
        kwargs = self._tween(self.kwargs.copy(),x)
        _x = x
        if self.x_max-self.x_min == 1:#handle 1 frame anims
            _x = self.x_max
        self.anim_function(_x,kwargs)
        self.check_transforms(x)

    def anim_function(self,x,kwargs):
        data_x = to_np_array(self.x)
        data_y = to_np_array(self.y)
        if self.__class__.__name__ == 'errorbar':
            data_x_err = to_np_array(self.xerr)
            data_y_err = to_np_array(self.yerr)
        elif self.__class__.__name__ == 'fill_between':
            y1 = to_np_array(self.y1)
            y2 = to_np_array(self.y2)
        elif self.__class__.__name__ == 'fill_betweenx':
            x1 = to_np_array(self.x1)
            x2 = to_np_array(self.x2)

        #First pass to get frame if sequencing
        for anim in self.anims:
            if anim['name'] != 'sequence':
                continue
            if self.x is None:
                continue
            if x < anim['delay'] or x > anim['delay'] + anim['duration']:
                continue

            t = self.get_t_from_x(anim,x)

            if len(data_x.shape) == 1:
                data_x = data_x.reshape((-1,1))
                data_y = data_y.reshape((-1,1))
            
            _i = max(min(round(t*len(data_x)),len(data_x)-1),0)
            data_x = data_x[_i]
            data_y = data_y[_i]
            
            if self.__class__.__name__ == 'errorbar':
                data_x_err = data_x_err[_i]
                data_y_err = data_y_err[_i]
            elif self.__class__.__name__ == 'fill_between':
                y1 = y1[_i]
                y2 = y2[_i]
            elif self.__class__.__name__ == 'fill_betweenx':
                x1 = x1[_i]
                x2 = x2[_i]

        #Second pass to cut points if drawing or erasing
        i_max = -1
        for anim in self.anims:
            if anim['name'] != 'draw':
                continue
            if self.x is None:
                continue
            if x < anim['delay'] or x > anim['delay'] + anim['duration']:
                continue
            t = self.get_t_from_x(anim,x)

            if 'alpha' in kwargs:
                alpha = to_np_array(kwargs['alpha'])
                if np.sum(alpha) == 0:
                    kwargs['alpha'] = 1

            if anim['reverse']:
                i_max = max(round((1-t)*len(data_x)),0)
            else:
                i_max = min(round(t*len(data_x)),len(data_x))
            break
        
        if i_max > 0:
            data_x = data_x[:i_max]
            if data_y is not None:
                data_y = data_y[:i_max]
            if self.__class__.__name__ == 'errorbar':
                data_x_err = data_x_err[:i_max]
                data_y_err = data_y_err[:i_max]
            elif self.__class__.__name__ == 'fill_between':
                y1 = y1[:i_max]
                y2 = y2[:i_max]
            elif self.__class__.__name__ == 'fill_betweenx':
                x1 = x1[:i_max]
                x2 = x2[:i_max]
            if 'c' in kwargs and isinstance(kwargs['c'],(list,np.ndarray)):
                kwargs['c'] = kwargs['c'][:i_max]
        elif i_max == 0:
            data_x = []
            data_y = []
            if self.__class__.__name__ == 'errorbar':
                data_x_err = []
                data_y_err = []
            elif self.__class__.__name__ == 'fill_between':
                y1 = []
                y2 = []
            elif self.__class__.__name__ == 'fill_betweenx':
                x1 = []
                x2 = []
            if 'c' in kwargs and isinstance(kwargs['c'],(list,np.ndarray)):
                kwargs['c'] = []

        #Third pass to morph
        for anim in self.anims:
            if anim['name'] != 'morph':
                continue
            if self.x is None:
                continue
            if x < anim['delay'] or x > anim['delay'] + anim['duration']:
                continue
            t = self.get_t_from_x(anim,x)

            if data_x is None or data_y is None:
                continue
            
            new_data_x = []
            new_data_y = []
            for i in range(len(data_x)):
                new_data_x.append(data_x[i] + (anim['new_x'][i] - data_x[i])*t)
                if len(data_y) == len(anim['new_y']):
                    new_data_y.append(data_y[i] + (anim['new_y'][i] - data_y[i])*t)
            data_x = new_data_x
            data_y = new_data_y

            if self.__class__.__name__ == 'errorbar':
                new_data_x_err = []
                new_data_y_err = []
                for i in range(len(data_x_err)):
                    new_data_x_err.append(data_x_err[i] + (anim['new_x_err'][i] - data_x_err[i])*t)
                    new_data_y_err.append(data_y_err[i] + (anim['new_y_err'][i] - data_y_err[i])*t)
                data_x_err = new_data_x_err
                data_y_err = new_data_y_err
        
        if self.__class__.__name__ == 'errorbar':
            kwargs['xerr'] = data_x_err
            kwargs['yerr'] = data_y_err
        elif self.__class__.__name__ == 'fill_between':
            kwargs['y1'] = y1
            kwargs['y2'] = y2
        elif self.__class__.__name__ == 'fill_betweenx':
            kwargs['x1'] = x1
            kwargs['x2'] = x2

        data_x = to_np_array(data_x)
        data_y = to_np_array(data_y)
        
        if self.function is not None:
            self.function(data_x,data_y,x,kwargs)

    def initialize(self,timeline):
        self.tl = timeline
        if self.axis is None:
            self.set_axis(self.tl.main_axis)
        
        self.clean(0)
        self.compute_timings()
        self.init()

    def compute_timings(self):
        x_max = 0
        x_min = np.inf
        for anim in self.anims:
            if anim['duration'] + anim['delay'] > x_max:
                x_max = anim['duration'] + anim['delay']
                self.persistent = anim['persistent']
            if anim['delay'] < x_min:
                x_min = anim['delay']
        self.x_max = x_max
        self.x_min = x_min

    def get_t_from_x(self,anim,x):
        easing = easings.easeLinear()
        if self.tl.easing is not None:
            easing = self.tl.easing
        if self.easing is not None:
            easing = self.easing
        if self.animate_easing is not None:
            easing = self.animate_easing
        if anim['easing'] is not None:
            easing = anim['easing']

        if anim['duration'] == 1 and x == anim['delay']:
            return 1
        return easing.ease((x - anim['delay']) / max(1, anim['duration'] - 1))

    def sanitize_colors(self,properties,starts,ends):
        for i in range(len(properties)):
            if properties[i] in ['c','colors','color','edgecolor','facecolor','edgecolors','facecolors']:
                starts[i] = list(mpl.colors.to_rgba_array(starts[i])[0])
                ends[i] = list(mpl.colors.to_rgba_array(ends[i])[0])
        return properties,starts,ends

    def plot(self,duration,delay=0,easing=None,persistent=True):
        """Plot the plot object as-is without animation.

        Parameters
        ----------
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        """
        self.anims.append({
            'name':'plot',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self

    def tween(self,property,start,end,duration,delay=0,easing=None,persistent=True):
        """Animate a change in a property of the plot object.

        Parameters
        ----------
        property : str
            the name of the property to animate.
        start : any
            the starting value of the property.
        end : any
            the ending value of the property.
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        """
        return self.tweens([property],[start],[end],duration,delay,easing,persistent=persistent)
    
    def tweens(self,properties,starts,ends,duration,delay=0,easing=None,persistent=True):
        """Animate multiple properties at once.

        Parameters
        ----------
        properties : list[str]
            a list of the names of the properties to animate.
        starts : list[Any]
            the starting values of the properties.
        ends : list[Any]
            the ending values of the properties.
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        """
        starts = [to_np_array(start) for start in starts]
        ends = [to_np_array(end) for end in ends]
        properties = self.get_main_alias(properties)
        properties,starts,ends = self.sanitize_colors(properties,starts,ends)
        
        for property,start,end in zip(properties,starts,ends):
            new_anim = {
                'name':'tween',
                'duration':duration,
                'delay':delay,
                'easing':easing,
                'property':property,
                'start':start,
                'end':end,
                'persistent':persistent,
                'played':False
            }
            self.anims.append(new_anim)
        self.compute_timings()
        return self
    
    def _tween(self,kwargs,x):
        for anim in self.anims:
            if x < anim['delay']:
                continue
            if anim['name'] != 'tween':
                continue
            _x = min(x,anim['duration'] + anim['delay'])
            t = self.get_t_from_x(anim,_x)
            t = np.clip(t,0,1)
            start = to_np_array(anim['start'])
            end = to_np_array(anim['end'])
            current = start + (end - start)*t
            kwargs[anim['property']] = current
        return kwargs

    def show(self,duration,delay=0,easing=None,persistent=True):
        """Fade in plot objects.

        This is a shorthand animation that fades in plot objects. It is equivalent to `tween('alpha',0,1)`.

        Parameters
        ----------
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.
        """
        return self.tween('alpha',start=0,end=1,duration=duration,delay=delay,easing=easing,persistent=persistent)

    def hide(self,duration,delay=0,easing=None,persistent=True):
        """Fade out plot objects.

        This is a shorthand animation that fades out plot objects. It is equivalent to `tween('alpha',1,0)`.

        Parameters
        ----------
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.
        """
        return self.tween('alpha',start=1,end=0,duration=duration,delay=delay,easing=easing,persistent=persistent)
    
    def draw(self,duration,reverse=False,delay=0,easing=None,persistent=True):
        """Animate the plot object by sequentially adding more points of the dataset.

        Parameters
        ----------
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        reverse : bool, default=False
            if True, removes points sequentially instead of adding points.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.
        """
        self.anims.append({
            'name':'draw',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'reverse':reverse,
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self
    
    def scale(self,start_scale,end_scale,duration,center=None,delay=0,easing=None,persistent=True):
        """Scale a plot object from one size to another.

        Parameters
        ----------
        start_scale : float or tuple[float, float]
            the starting scale of the plot object.
        end_scale : float or tuple[float, float]
            the ending scale of the plot object.
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.

        You can either pass scalar values, in which case the plot object will be uniformly scaled, or a 2-tuple for independent X and Y scales.
        """
        if isinstance(start_scale,(list,tuple,np.ndarray)):
            scalex_start,scaley_start = start_scale
        else:
            scalex_start = start_scale
            scaley_start = start_scale
        if isinstance(end_scale,(list,tuple,np.ndarray)):
            scalex_end,scaley_end = end_scale
        else:
            scalex_end = end_scale
            scaley_end = end_scale
        
        self.anims.append({
            'name':'scale',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'start':(scalex_start,scaley_start),
            'end':(scalex_end,scaley_end),
            'persistent':persistent,
            'center':center,
            'played':False
        })
        self.compute_timings()
        return self
    
    def _scale(self, t, start, end, center=None):
        if center is None:
            cx, cy = self.get_center()
        else:
            cx, cy = center
        scale_x = start[0] + (end[0] - start[0]) * t
        scale_y = start[1] + (end[1] - start[1]) * t

        # Update Affine2D for non-collections
        self.T = (
            self.T
            .translate(-cx, -cy)
            .scale(scale_x, scale_y)
            .translate(cx, cy)
        )

        obj = to_np_array(self.obj)
        for o in obj:
            if isinstance(o, mpl.collections.Collection) and self.mpl_obj_type == mpl.collections.Collection:
                offsets = np.asarray(o.get_offsets(), dtype=float).reshape(-1, 2)
                offsets_centered = offsets - np.array([cx, cy])

                new_offsets = offsets_centered * np.array([scale_x, scale_y]) + np.array([cx, cy])

                new_offsets = new_offsets.reshape(-1, 2)
                o.set_offsets(new_offsets)
            else:
                o.set_transform(self.T + self.axis.transData)

    def rotate(self,start_angle,end_angle,duration,center=None,delay=0,easing=None,persistent=True):
        """Rotate a plot object from one angle to another.

        Parameters
        ----------
        start_angle : float
            the starting angle of the rotation in radians.
        end_angle : float
            the ending angle of the rotation in radians.
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.
        """
        self.anims.append({
            'name':'rotate',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'start':start_angle,
            'end':end_angle,
            'center':center,
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self
    
    def _rotate(self, t, start, end, center=None):
        if center is None:
            cx, cy = self.get_center()
        else:
            cx, cy = center
        rotation = start + (end - start) * t
        self.T = (
            self.T
            .translate(-cx, -cy)
            .rotate_deg(rotation)
            .translate(cx, cy)
        )
        
        obj = to_np_array(self.obj)
        for o in obj:            
            if isinstance(o, mpl.collections.Collection) and self.mpl_obj_type == mpl.collections.Collection:
                offsets = np.asarray(o.get_offsets(), dtype=float).reshape(-1, 2)
                offsets_centered = offsets - np.array([cx, cy])
                
                theta = np.deg2rad(rotation)
                R = np.array([[np.cos(theta), -np.sin(theta)],
                            [np.sin(theta),  np.cos(theta)]])
                
                new_offsets = offsets_centered @ R.T + np.array([cx, cy])
                
                new_offsets = new_offsets.reshape(-1, 2)
                o.set_offsets(new_offsets)
            else:
                o.set_transform(self.T + self.axis.transData)
    
    def translate(self,start_pos,end_pos,duration,delay=0,easing=None,persistent=True):
        """Move a plot object from one position to another.

        Parameters
        ----------
        start_pos : array-like
            where the translation starts, relative to the current center of the plot object.
        end_pos : array-like
            where the translation ends, relative to the current center of the plot object.
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.
        """
        self.anims.append({
            'name':'translate',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'start':start_pos,
            'end':end_pos,
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self
    
    def _translate(self,t,start,end):
        pos_x = start[0] + (end[0] - start[0])*t
        pos_y = start[1] + (end[1] - start[1])*t
        self.T = self.T.translate(pos_x,pos_y)
        obj = to_np_array(self.obj)
        for o in obj:
            if self.mpl_obj_type == mpl.collections.Collection:
                offsets = o.get_offsets()
                o.set_offsets(offsets + np.array([pos_x,pos_y]))
            else:
                o.set_transform(self.T + self.axis.transData)
    
    def morph(self,new_x,new_y,duration,delay=0,easing=None,persistent=True):
        """Morph between the base dataset and a new dataset.

        Parameters
        ----------
        new_x : array-like or float
            the x data points to morph to.
        new_y : array-like or float
            the y data points to morph to.
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.

        For plot objects that take 1D datasets (e.g. hist()), `morph()` only accepts `new_x`.
        """
        # TODO : if new_x/new_y not the same size, resample them to match
        if isinstance(new_x,numbers.Number):
            new_x = [new_x]
            new_y = [new_y]
        new_x = to_np_array(new_x)
        new_y = to_np_array(new_y)
        
        self.anims.append({
            'name':'morph',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'new_x':new_x,
            'new_y':new_y,
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self
    
    def sequence(self,duration,delay=0,easing=None,persistent=True):
        """Plot one datapoint or row of the dataset per frame.

        Parameters
        ----------
        duration : float
            the number of frames the animation runs from.
        delay : float, default=0
            the number of frames after what the animation starts playing.
        easing : callable, optional
            the easing used for this animation. If None, a linear easing is applied.
        persistent : bool, default=True
            if True, the plot object will continue to be plotted after its last animation has played.

        If the dataset is 1-dimensional, this plots a single datapoint per frame, if 2D, it will plot one row per frame. This animation can be used if you have a predefined list of datapoints you want to animate frame-by-frame.
        """
        self.anims.append({
            'name':'sequence',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self

    def clean(self,x,clear_anims=True):
        if self.obj is not None and self.base_color is None:
            if isinstance(self.obj,(list,np.ndarray)):
                self.base_color = self.obj[0].get_color()    
            elif hasattr(self.obj,'get_color'):
                self.base_color = self.obj.get_color()
            if 'color' not in self.kwargs and 'c' not in self.kwargs and self.base_color is not None:
                self.kwargs['color'] = self.base_color

        for anim in self.anims:
            t = self.get_t_from_x(anim,x)
            if t != 1:
                continue
            if anim['name'] == 'morph':
                self.x = anim['new_x']
                self.y = anim['new_y']

        if x >= self.x_min-1 and x < self.x_max-1 and self.obj is not None:
            if isinstance(self.obj,list):
                for obj in self.obj:
                    try:
                        obj.remove()
                    except:
                        pass
            else:
                try:
                    self.obj.remove()
                except:
                    pass
            self.obj = None
        elif x == self.x_max and clear_anims:
            self.end_animation()
            
    def end_animation(self):
        self.anims = []

    def clean_kwargs(self,kwargs):
        if 'duration' in kwargs:
            del kwargs['duration']
        if 'delay' in kwargs:
            del kwargs['delay']
        if 'easing' in kwargs:
            del kwargs['delay']
        if 'axis' in kwargs:
            del kwargs['axis']
        return kwargs
    
    def check_transforms(self,x):
        if self.mpl_obj_type is None:
            return
        for anim in self.anims:
            if x < anim['delay']:
                continue
            _x = min(x,anim['duration'] + anim['delay']-1)
            
            t = self.get_t_from_x(anim,_x)
            if anim['name'] == 'scale':
                start = to_np_array(anim['start'])
                end = to_np_array(anim['end'])
                self._scale(t,start,end,center=anim['center'])
            if anim['name'] == 'translate':
                start = to_np_array(anim['start'])
                end = to_np_array(anim['end'])
                self._translate(t,start,end)
            if anim['name'] == 'rotate':
                start = to_np_array(anim['start'])
                end = to_np_array(anim['end'])
                self._rotate(t,start,end,center=anim['center'])

    def get_center(self):
        if self.mpl_obj_type == mpl.lines.Line2D:
            bbox = self.obj[0].get_bbox().get_points()
            cx = (bbox[0][0] + bbox[1][0])/2
            cy = (bbox[0][1] + bbox[1][1])/2
        elif self.mpl_obj_type == mpl.patches.PathPatch:
            bbox = self.path.get_extents()
            cx = (bbox.x0 + bbox.x1) / 2
            cy = (bbox.y0 + bbox.y1) / 2
        elif self.mpl_obj_type == mpl.contour.QuadContourSet:
            bboxes = [p.get_extents() for p in self.obj.get_paths()]
            bbox = mpl.transforms.Bbox.union(bboxes)
            cx = (bbox.x0 + bbox.x1) / 2
            cy = (bbox.y0 + bbox.y1) / 2
        elif self.mpl_obj_type == mpl.collections.Collection:
            offsets = self.obj.get_offsets()
            if len(offsets) == 0:
                cx,cy = 0,0
            else:
                cx = np.mean(offsets[:, 0])
                cy = np.mean(offsets[:, 1])
        elif self.mpl_obj_type == mpl.collections.QuadMesh:
            coords = self.obj.get_coordinates()
            x0 = np.nanmin(coords[..., 0])
            x1 = np.nanmax(coords[..., 0])
            y0 = np.nanmin(coords[..., 1])
            y1 = np.nanmax(coords[..., 1])

            cx = 0.5 * (x0 + x1)
            cy = 0.5 * (y0 + y1)
        elif self.mpl_obj_type == mpl.patches.Rectangle:
            rects = self.obj.patches
            if isinstance(rects, list) and len(rects) > 0:
                centers_x = []
                centers_y = []
                for rect in rects:
                    bbox = rect.get_bbox()
                    cx = (bbox.x0 + bbox.x1) / 2
                    cy = (bbox.y0 + bbox.y1) / 2
                    centers_x.append(cx)
                    centers_y.append(cy)
                cx = np.mean(centers_x)
                cy = np.mean(centers_y)
            else:
                bbox = self.obj.get_bbox()
                cx = (bbox.x0 + bbox.x1) / 2
                cy = (bbox.y0 + bbox.y1) / 2
        elif self.mpl_obj_type == mpl.collections.FillBetweenPolyCollection:
            bboxes = [p.get_extents() for p in self.obj.get_paths() if p.vertices.size]
            bbox = mpl.transforms.Bbox.union(bboxes)
            cx = 0.5 * (bbox.x0 + bbox.x1)
            cy = 0.5 * (bbox.y0 + bbox.y1)
        return (cx,cy)

class axis_zoom(plotObject):
    """
    Zooms into the axis given a zoom value.

    Parameters
    ----------
    zoom : float
        Zoom level
    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on
    """
    def __init__(self,zoom,duration,delay=0,easing=None,axis=None,*args,**kwargs):
        super().__init__(axis=axis,*args, **kwargs)
        self.anims = [{
            'name':'axis_move',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':True,
            'zoom':zoom,
            'played':False
        }]
        self.compute_timings()

    def init(self):
        if 'start_width' not in self.anims[0]:
            self.anims[0]['start_width'] = self.axis.get_xlim()[1] - self.axis.get_xlim()[0]
            self.anims[0]['start_height'] = self.axis.get_ylim()[1] - self.axis.get_ylim()[0]
            self.anims[0]['end_width'] = self.anims[0]['start_width']/self.anims[0]['zoom']
            self.anims[0]['end_height'] = self.anims[0]['start_height']/self.anims[0]['zoom']

    def function(self,data_x,data_y,x,kwargs):
        anim = self.anims[0]
        if x < anim['delay']:
            return
        _x = min(x,anim['duration'] + anim['delay']-1)
        t = self.get_t_from_x(anim,x)
    
        center = ((self.axis.get_xlim()[1]+self.axis.get_xlim()[0])/2,(self.axis.get_ylim()[1]+self.axis.get_ylim()[0])/2)
        width = anim['start_width'] + (anim['end_width'] - anim['start_width'])*t
        height = anim['start_height'] + (anim['end_height'] - anim['start_height'])*t
        x_range = (center[0] - width/2, center[0] + width/2)
        y_range = (center[1] - height/2, center[1] + height/2)
        self.axis.set_xlim(x_range[0],x_range[1])
        self.axis.set_ylim(y_range[0],y_range[1])

class axis_limits(plotObject):
    """
    Reframe axis to the given limits (on the x-axis, y-axis or both depending on passed arguments)

    Parameters
    ----------
    xlim : array-like, default=None
        Target limits of the x-axis
    ylim : array-like, default=None
        Target limits of the y-axis
    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on
    """
    def __init__(self,duration,xlim=None,ylim=None,delay=0,easing=None,axis=None,*args,**kwargs):
        if xlim is None and ylim is None:
            raise ValueError('Both xlim and ylim cannot be empty.')
        super().__init__(axis=axis,*args, **kwargs)
        self.anims = [{
            'name':'axis_move',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':True,
            'xlim':xlim,
            'ylim':ylim,
            'played':False
        }]
        self.compute_timings()

    def init(self):
        if 'start_xlim' not in self.anims[0]:
            self.anims[0]['start_xlim'] = self.axis.get_xlim()
            self.anims[0]['start_ylim'] = self.axis.get_ylim()

    def function(self,data_x,data_y,x,kwargs):
        anim = self.anims[0]
        if x < anim['delay']:
            return
        _x = min(x,anim['duration'] + anim['delay']-1)
        t = self.get_t_from_x(anim,x)

        if anim['xlim'] is not None:
            xlim_left   = anim['start_xlim'][0] + (anim['xlim'][0] - anim['start_xlim'][0])*t
            xlim_right  = anim['start_xlim'][1] + (anim['xlim'][1] - anim['start_xlim'][1])*t
            self.axis.set_xlim(xlim_left,xlim_right)
        if anim['ylim'] is not None:
            ylim_bottom = anim['start_ylim'][0] + (anim['ylim'][0] - anim['start_ylim'][0])*t
            ylim_top    = anim['start_ylim'][1] + (anim['ylim'][1] - anim['start_ylim'][1])*t
            self.axis.set_ylim(ylim_bottom,ylim_top)

class axis_move(plotObject):
    """
    Move the center of the axis to a given position.

    Parameters
    ----------
    pos : array-like
        Target center position
    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on
    """
    def __init__(self,end_pos,duration,start_pos=None,delay=0,easing=None,axis=None,*args,**kwargs):
        super().__init__(axis=axis,*args, **kwargs)
        self.anims = [{
            'name':'axis_move',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':True,
            'start':start_pos,
            'end':end_pos,
            'played':False
        }]
        self.compute_timings()

    def init(self):
        if self.anims[0]['start'] is None:
            self.anims[0]['start'] = [
                (self.axis.get_xlim()[0]+self.axis.get_xlim()[1])/2,
                (self.axis.get_ylim()[0]+self.axis.get_ylim()[1])/2,
            ]

    def function(self,data_x,data_y,x,kwargs):
        anim = self.anims[0]
        if x < anim['delay']:
            return
        _x = min(x,anim['duration'] + anim['delay']-1)
        t = self.get_t_from_x(anim,x)
        width  = self.axis.get_xlim()[1]-self.axis.get_xlim()[0]
        height = self.axis.get_ylim()[1]-self.axis.get_ylim()[0]
        pos_x = anim['start'][0] + (anim['end'][0] - anim['start'][0])*t
        pos_y = anim['start'][1] + (anim['end'][1] - anim['start'][1])*t
        self.axis.set_xlim(pos_x-width/2,pos_x+width/2)
        self.axis.set_ylim(pos_y-height/2,pos_y+height/2)

class axis_alpha(plotObject):
    """
    Change the opacity of the axis.

    Parameters
    ----------
    start_alpha : float
        Initial alpha value
    end_alpha : float
        Final alpha value
    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on
    """
    def __init__(self,start_alpha,end_alpha,duration,delay=0,alpha_objs=True,easing=None,axis=None,*args,**kwargs):
        super().__init__(axis=axis,*args, **kwargs)
        self.anims = [{
            'name':'axis_move',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':True,
            'start':start_alpha,
            'end':end_alpha,
            'alpha_objs':alpha_objs,
            'played':False
        }]
        self.compute_timings()

    def init(self):
        pass

    def function(self,data_x,data_y,x,kwargs):
        anim = self.anims[0]
        if x < anim['delay']:
            return
        _x = min(x,anim['duration'] + anim['delay']-1)
        t = self.get_t_from_x(anim,x)
        alpha = anim['start'] + (anim['end'] - anim['start'])*t
        alpha = np.clip(alpha,0,1)
        
        self.axis.patch.set_alpha(alpha)

        for spine in self.axis.spines.values():
            spine.set_alpha(alpha)

        for tick in self.axis.xaxis.get_major_ticks() + self.axis.yaxis.get_major_ticks():
            for line in tick.tick1line, tick.tick2line:
                line.set_alpha(alpha)
            label = tick.label1
            label.set_alpha(alpha)

        self.axis.xaxis.label.set_alpha(alpha)
        self.axis.yaxis.label.set_alpha(alpha)

        self.axis.title.set_alpha(alpha)

        if anim['alpha_objs']:
            for line in self.axis.get_xgridlines() + self.axis.get_ygridlines():
                line.set_alpha(alpha)
            for line in self.axis.lines:
                line.set_alpha(alpha)
            for col in self.axis.collections:
                col.set_alpha(alpha)
            for patch in self.axis.patches:
                patch.set_alpha(alpha)
            for img in self.axis.images:
                img.set_alpha(alpha)
            for txt in self.axis.texts:
                txt.set_alpha(alpha)
            leg = self.axis.get_legend()
            if leg:
                leg.get_frame().set_alpha(alpha)
                for txt in leg.get_texts():
                    txt.set_alpha(alpha)

class fig_width_ratio(plotObject):
    """
    Resize subplots' widths.

    Parameters
    ----------
    start_widths : array-like
        Starting width ratios
    end_widths : array-like
        End width ratios
    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on
    """
    def __init__(self,start_widths,end_widths,duration,delay=0,easing=None,axis=None,*args,**kwargs):
        super().__init__(axis=axis,*args, **kwargs)
        self.grid = None
        start_widths = to_np_array(start_widths).astype(float)
        end_widths = to_np_array(end_widths).astype(float)
        start_widths = np.maximum(start_widths,1e-3)
        end_widths = np.maximum(end_widths,1e-3)
        #Normalize the ratios so scaling with time remains linear
        start_widths = start_widths/np.sum(start_widths)
        end_widths = end_widths/np.sum(end_widths)
        self.anims = [{
            'name':'axis_move',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':True,
            'start':start_widths,
            'end':end_widths,
            'played':False
        }]
        self.compute_timings()

    def init(self):
        if self.tl.fig.get_layout_engine() is None:
            #Band-aid fix
            self.tl.fig.set_layout_engine('tight')
        if self.grid is None:
            self.grid = self.axis.get_gridspec()

    def function(self,data_x,data_y,x,kwargs):
        anim = self.anims[0]
        if x < anim['delay']:
            return
        _x = min(x,anim['duration'] + anim['delay']-1)
        t = self.get_t_from_x(anim,x)
        
        widths = anim['start'] + (anim['end'] - anim['start'])*t
        
        self.grid.set_width_ratios(widths)

        axes = to_np_array(self.tl.fig.get_axes())
        shape = self.tl.fig.axes[0].get_subplotspec().get_gridspec().get_geometry()
        axes = axes.reshape(shape)        
        for i in range(len(widths)):
            if widths[i] < 1e-3:
                for row in axes:
                    row[i].set_axis_off()
            else:
                for row in axes:
                    if row[i].axison == False:
                        row[i].set_axis_on()

class fig_height_ratio(plotObject):
    """
    Resize subplots' heights.

    Parameters
    ----------
    start_heights : array-like
        Starting height ratios
    end_heights : array-like
        End height ratios
    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on
    """
    def __init__(self,start_heights,end_heights,duration,delay=0,easing=None,axis=None,*args,**kwargs):
        super().__init__(axis=axis,*args, **kwargs)
        self.grid = None
        start_heights = to_np_array(start_heights)
        end_heights = to_np_array(end_heights)
        start_heights = np.maximum(start_heights,1e-3)
        end_heights = np.maximum(end_heights,1e-3)
        #Normalize the ratios so scaling with time remains linear
        start_heights = start_heights/np.sum(start_heights)
        end_heights = end_heights/np.sum(end_heights)
        self.anims = [{
            'name':'axis_move',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'persistent':True,
            'start':start_heights,
            'end':end_heights,
            'played':False
        }]
        self.compute_timings()

    def init(self):
        if self.tl.fig.get_layout_engine() is None:
            #Band-aid fix
            self.tl.fig.set_layout_engine('tight')
        if self.grid is None:
            self.grid = self.axis.get_gridspec()

    def function(self,data_x,data_y,x,kwargs):
        anim = self.anims[0]
        if x < anim['delay']:
            return
        _x = min(x,anim['duration'] + anim['delay']-1)
        t = self.get_t_from_x(anim,x)
        
        heights = anim['start'] + (anim['end'] - anim['start'])*t
        
        self.grid.set_height_ratios(heights)

        axes = to_np_array(self.tl.fig.get_axes())
        shape = self.tl.fig.axes[0].get_subplotspec().get_gridspec().get_geometry()
        axes = axes.reshape(shape)
        for i in range(len(heights)):
            if heights[i] < 1e-3:
                for column in axes.T:
                    column[i].set_axis_off()
            else:
                for column in axes.T:
                    if column[i].axison == False:
                        column[i].set_axis_on()

class scatter(plotObject):
    """
    A scatter plot of *y* vs. *x* with varying marker size and/or color.

    Parameters
    ----------
    x, y : float or array-like, shape (n, )
        The data positions.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    s : float or array-like, shape (n, ), optional
        The marker size in points**2 (typographic points are 1/72 in.).
        Default is ``rcParams['lines.markersize'] ** 2``.

        The linewidth and edgecolor can visually interact with the marker
        size, and can lead to artifacts if the marker size is smaller than
        the linewidth.

        If the linewidth is greater than 0 and the edgecolor is anything
        but *'none'*, then the effective size of the marker will be
        increased by half the linewidth because the stroke will be centered
        on the edge of the shape.

        To eliminate the marker edge either set *linewidth=0* or
        *edgecolor='none'*.

    c : array-like or list of color or color, optional
        The marker colors. Possible values:

        - A scalar or sequence of n numbers to be mapped to colors using
          *cmap* and *norm*.
        - A 2D array in which the rows are RGB or RGBA.
        - A sequence of colors of length n.
        - A single color format string.

        Note that *c* should not be a single numeric RGB or RGBA sequence
        because that is indistinguishable from an array of values to be
        colormapped. If you want to specify the same RGB or RGBA value for
        all points, use a 2D array with a single row.  Otherwise,
        value-matching will have precedence in case of a size matching with
        *x* and *y*.

        If you wish to specify a single color for all points
        prefer the *color* keyword argument.

        Defaults to `None`. In that case the marker color is determined
        by the value of *color*, *facecolor* or *facecolors*. In case
        those are not specified or `None`, the marker color is determined
        by the next color of the ``Axes``' current "shape and fill" color
        cycle. This cycle defaults to axes.prop_cycle.

    marker : `~.markers.MarkerStyle`, default: scatter.marker
        The marker style. *marker* can be either an instance of the class
        or the text shorthand for a particular marker.
        See :mod:`matplotlib.markers` for more information about marker
        styles.

    cmap : str or `~matplotlib.colors.Colormap`, default: image.cmap
        The Colormap instance or registered colormap name used to map scalar data
        to colors.

        This parameter is ignored if *c* is RGB(A).

    norm : str or `~matplotlib.colors.Normalize`, optional
        The normalization method used to scale scalar data to the [0, 1] range
        before mapping to colors using *cmap*. By default, a linear scaling is
        used, mapping the lowest value to 0 and the highest to 1.

        If given, this can be one of the following:

        - An instance of `.Normalize` or one of its subclasses
          (see :ref:`colormapnorms`).
        - A scale name, i.e. one of "linear", "log", "symlog", "logit", etc.  For a
          list of available scales, call `matplotlib.scale.get_scale_names()`.
          In that case, a suitable `.Normalize` subclass is dynamically generated
          and instantiated.

        This parameter is ignored if *c* is RGB(A).

    vmin, vmax : float, optional
        When using scalar data and no explicit *norm*, *vmin* and *vmax* define
        the data range that the colormap covers. By default, the colormap covers
        the complete value range of the supplied data. It is an error to use
        *vmin*/*vmax* when a *norm* instance is given (but using a `str` *norm*
        name together with *vmin*/*vmax* is acceptable).

        This parameter is ignored if *c* is RGB(A).

    alpha : float, default: None
        The alpha blending value, between 0 (transparent) and 1 (opaque).

    linewidths : float or array-like, default: lines.linewidth
        The linewidth of the marker edges. Note: The default *edgecolors*
        is 'face'. You may want to change this as well.

    edgecolors : {'face', 'none', *None*} or color or list of color, default: scatter.edgecolors
        The edge color of the marker. Possible values:

        - 'face': The edge color will always be the same as the face color.
        - 'none': No patch boundary will be drawn.
        - A color or sequence of colors.

        For non-filled markers, *edgecolors* is ignored. Instead, the color
        is determined like with 'face', i.e. from *c*, *colors*, or
        *facecolors*.

    colorizer : `~matplotlib.colorizer.Colorizer` or None, default: None
        The Colorizer object used to map color to data. If None, a Colorizer
        object is created from a *norm* and *cmap*.

        This parameter is ignored if *c* is RGB(A).

    plotnonfinite : bool, default: False
        Whether to plot points with nonfinite *c* (i.e. ``inf``, ``-inf``
        or ``nan``). If ``True`` the points are drawn with the *bad*
        colormap color (see `.Colormap.set_bad`).

    Returns
    -------
    `~matplotlib.collections.PathCollection`

    Other Parameters
    ----------------
    data : indexable object, optional
        If given, the following parameters also accept a string ``s``, which is
        interpreted as ``data[s]`` if ``s`` is a key in ``data``:

        *x*, *y*, *s*, *linewidths*, *edgecolors*, *c*, *facecolor*, *facecolors*, *color*
    **kwargs : `~matplotlib.collections.PathCollection` properties
        Properties:
        agg_filter: a filter function, which takes a (m, n, 3) float array and a dpi value, and returns a (m, n, 3) array and two offsets from the bottom left corner of the image
        alpha: array-like or float or None
        animated: bool
        antialiased or aa or antialiaseds: bool or list of bools
        array: array-like or None
        capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        clim: (vmin: float, vmax: float)
        clip_box: `~matplotlib.transforms.BboxBase` or None
        clip_on: bool
        clip_path: Patch or (Path, Transform) or None
        cmap: `.Colormap` or str or None
        color: color or list of RGBA tuples
        edgecolor or ec or edgecolors: color or list of color or 'face'
        facecolor or facecolors or fc: color or list of color
        figure: `~matplotlib.figure.Figure` or `~matplotlib.figure.SubFigure`
        gid: str
        hatch: {'/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*'}
        hatch_linewidth: unknown
        in_layout: bool
        joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        label: object
        linestyle or dashes or linestyles or ls: str or tuple or list thereof
        linewidth or linewidths or lw: float or list of floats
        mouseover: bool
        norm: `.Normalize` or str or None
        offset_transform or transOffset: `.Transform`
        offsets: (N, 2) or (2,) array-like
        path_effects: list of `.AbstractPathEffect`
        paths: unknown
        picker: None or bool or float or callable
        pickradius: float
        rasterized: bool
        sizes: `numpy.ndarray` or None
        sketch_params: (scale: float, length: float, randomness: float)
        snap: bool or None
        transform: `~matplotlib.transforms.Transform`
        url: str
        urls: list of str or None
        visible: bool
        zorder: float

    See Also
    --------
    plot : To plot scatter plots when markers are identical in size and
        color.

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.scatter`.

    * The `.plot` function will be faster for scatterplots where markers
      don't vary in size or color.

    * Any or all of *x*, *y*, *s*, and *c* may be masked arrays, in which
      case all masks will be combined and only unmasked points will be
      plotted.

    * Fundamentally, scatter works with 1D arrays; *x*, *y*, *s*, and *c*
      may be input as N-D arrays, but within scatter they will be
      flattened. The exception is *c*, which will be flattened only if its
      size matches the size of *x* and *y*.
    """
    def __init__(self,x,y,easing=None,axis=None,*args,**kwargs):
        self.mpl_obj_type = mpl.collections.Collection
        self.mpl_plot_type = plt.plot
        super().__init__(easing=easing,axis=axis,*args, **kwargs)

        self.x = to_np_array(x)
        self.y = to_np_array(y)
        if self.x.size != self.y.size:
            raise ValueError("x and y must be the same size")
    
    def clean(self,x,clear_anims=True):
        if self.obj is not None and self.base_color is None:
            self.base_color = self.obj.get_edgecolors()[0]
            if 'color' not in self.kwargs and 'c' not in self.kwargs:
                self.kwargs['color'] = self.base_color
        super().clean(x,clear_anims)
    
    def function(self,data_x,data_y,x,kwargs):
        if 'c' in kwargs and 'color' in kwargs:
            kwargs.pop('color')
        if 'c' in kwargs:
            c = to_np_array(kwargs['c'])
            if c.ndim == 1 and (len(c) == 3 or len(c) == 4) and len(c) != len(data_x) and (c <= 1).all():
                kwargs['c'] = c.reshape(1,-1)

        self.obj = self.axis.scatter(data_x,data_y,**kwargs)

class plot(plotObject):
    """
    Plot y versus x as lines and/or markers.

    Call signatures::

        plot([x], y, [fmt], *, data=None, **kwargs)
        plot([x], y, [fmt], [x2], y2, [fmt2], ..., **kwargs)

    The coordinates of the points or line nodes are given by *x*, *y*.

    The optional parameter *fmt* is a convenient way for defining basic
    formatting like color, marker and linestyle. It's a shortcut string
    notation described in the *Notes* section below.

    >>> plot(x, y)        # plot x and y using default line style and color
    >>> plot(x, y, 'bo')  # plot x and y using blue circle markers
    >>> plot(y)           # plot y using x as index array 0..N-1
    >>> plot(y, 'r+')     # ditto, but with red plusses

    You can use `.Line2D` properties as keyword arguments for more
    control on the appearance. Line properties and *fmt* can be mixed.
    The following two calls yield identical results:

    >>> plot(x, y, 'go--', linewidth=2, markersize=12)
    >>> plot(x, y, color='green', marker='o', linestyle='dashed',
    ...      linewidth=2, markersize=12)

    When conflicting with *fmt*, keyword arguments take precedence.


    **Plotting labelled data**

    There's a convenient way for plotting objects with labelled data (i.e.
    data that can be accessed by index ``obj['y']``). Instead of giving
    the data in *x* and *y*, you can provide the object in the *data*
    parameter and just give the labels for *x* and *y*::

    >>> plot('xlabel', 'ylabel', data=obj)

    All indexable objects are supported. This could e.g. be a `dict`, a
    `pandas.DataFrame` or a structured numpy array.


    **Plotting multiple sets of data**

    There are various ways to plot multiple sets of data.

    - The most straight forward way is just to call `plot` multiple times.
      Example:

      >>> plot(x1, y1, 'bo')
      >>> plot(x2, y2, 'go')

    - If *x* and/or *y* are 2D arrays, a separate data set will be drawn
      for every column. If both *x* and *y* are 2D, they must have the
      same shape. If only one of them is 2D with shape (N, m) the other
      must have length N and will be used for every data set m.

      Example:

      >>> x = [1, 2, 3]
      >>> y = np.array([[1, 2], [3, 4], [5, 6]])
      >>> plot(x, y)

      is equivalent to:

      >>> for col in range(y.shape[1]):
      ...     plot(x, y[:, col])

    - The third way is to specify multiple sets of *[x]*, *y*, *[fmt]*
      groups::

      >>> plot(x1, y1, 'g^', x2, y2, 'g-')

      In this case, any additional keyword argument applies to all
      datasets. Also, this syntax cannot be combined with the *data*
      parameter.

    By default, each line is assigned a different style specified by a
    'style cycle'. The *fmt* and line property parameters are only
    necessary if you want explicit deviations from these defaults.
    Alternatively, you can also change the style cycle using
    axes.prop_cycle.


    Parameters
    ----------
    x, y : array-like or float
        The horizontal / vertical coordinates of the data points.
        *x* values are optional and default to ``range(len(y))``.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


        Commonly, these parameters are 1D arrays.

        They can also be scalars, or two-dimensional (in that case, the
        columns represent separate data sets).

        These arguments cannot be passed as keywords.

    fmt : str, optional
        A format string, e.g. 'ro' for red circles. See the *Notes*
        section for a full description of the format strings.

        Format strings are just an abbreviation for quickly setting
        basic line properties. All of these and more can also be
        controlled by keyword arguments.

        This argument cannot be passed as keyword.

    data : indexable object, optional
        An object with labelled data. If given, provide the label names to
        plot in *x* and *y*.

        .. note::
            Technically there's a slight ambiguity in calls where the
            second label is a valid *fmt*. ``plot('n', 'o', data=obj)``
            could be ``plt(x, y)`` or ``plt(y, fmt)``. In such cases,
            the former interpretation is chosen, but a warning is issued.
            You may suppress the warning by adding an empty format string
            ``plot('n', 'o', '', data=obj)``.

    Returns
    -------
    list of `.Line2D`
        A list of lines representing the plotted data.

    Other Parameters
    ----------------
    scalex, scaley : bool, default: True
        These parameters determine if the view limits are adapted to the
        data limits. The values are passed on to
        `~.axes.Axes.autoscale_view`.

    **kwargs : `~matplotlib.lines.Line2D` properties, optional
        *kwargs* are used to specify properties like a line label (for
        auto legends), linewidth, antialiasing, marker face color.
        Example::

        >>> plot([1, 2, 3], [1, 2, 3], 'go-', label='line 1', linewidth=2)
        >>> plot([1, 2, 3], [1, 4, 9], 'rs', label='line 2')

        If you specify multiple lines with one plot call, the kwargs apply
        to all those lines. In case the label object is iterable, each
        element is used as labels for each set of data.

        Here is a list of available `.Line2D` properties:

        Properties:
        agg_filter: a filter function, which takes a (m, n, 3) float array and a dpi value, and returns a (m, n, 3) array and two offsets from the bottom left corner of the image
        alpha: float or None
        animated: bool
        antialiased or aa: bool
        clip_box: `~matplotlib.transforms.BboxBase` or None
        clip_on: bool
        clip_path: Patch or (Path, Transform) or None
        color or c: color
        dash_capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        dash_joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        dashes: sequence of floats (on/off ink in points) or (None, None)
        data: (2, N) array or two 1D arrays
        drawstyle or ds: {'default', 'steps', 'steps-pre', 'steps-mid', 'steps-post'}, default: 'default'
        figure: `~matplotlib.figure.Figure` or `~matplotlib.figure.SubFigure`
        fillstyle: {'full', 'left', 'right', 'bottom', 'top', 'none'}
        gapcolor: color or None
        gid: str
        in_layout: bool
        label: object
        linestyle or ls: {'-', '--', '-.', ':', '', (offset, on-off-seq), ...}
        linewidth or lw: float
        marker: marker style string, `~.path.Path` or `~.markers.MarkerStyle`
        markeredgecolor or mec: color
        markeredgewidth or mew: float
        markerfacecolor or mfc: color
        markerfacecoloralt or mfcalt: color
        markersize or ms: float
        markevery: None or int or (int, int) or slice or list[int] or float or (float, float) or list[bool]
        mouseover: bool
        path_effects: list of `.AbstractPathEffect`
        picker: float or callable[[Artist, Event], tuple[bool, dict]]
        pickradius: float
        rasterized: bool
        sketch_params: (scale: float, length: float, randomness: float)
        snap: bool or None
        solid_capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        solid_joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        transform: unknown
        url: str
        visible: bool
        xdata: 1D array
        ydata: 1D array
        zorder: float

    See Also
    --------
    scatter : XY scatter plot with markers of varying size and/or color (
        sometimes also called bubble chart).

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.plot`.

    **Format Strings**

    A format string consists of a part for color, marker and line::

        fmt = '[marker][line][color]'

    Each of them is optional. If not provided, the value from the style
    cycle is used. Exception: If ``line`` is given, but no ``marker``,
    the data will be a line without markers.

    Other combinations such as ``[color][marker][line]`` are also
    supported, but note that their parsing may be ambiguous.

    **Markers**

    =============   ===============================
    character       description
    =============   ===============================
    ``'.'``         point marker
    ``','``         pixel marker
    ``'o'``         circle marker
    ``'v'``         triangle_down marker
    ``'^'``         triangle_up marker
    ``'<'``         triangle_left marker
    ``'>'``         triangle_right marker
    ``'1'``         tri_down marker
    ``'2'``         tri_up marker
    ``'3'``         tri_left marker
    ``'4'``         tri_right marker
    ``'8'``         octagon marker
    ``'s'``         square marker
    ``'p'``         pentagon marker
    ``'P'``         plus (filled) marker
    ``'*'``         star marker
    ``'h'``         hexagon1 marker
    ``'H'``         hexagon2 marker
    ``'+'``         plus marker
    ``'x'``         x marker
    ``'X'``         x (filled) marker
    ``'D'``         diamond marker
    ``'d'``         thin_diamond marker
    ``'|'``         vline marker
    ``'_'``         hline marker
    =============   ===============================

    **Line Styles**

    =============    ===============================
    character        description
    =============    ===============================
    ``'-'``          solid line style
    ``'--'``         dashed line style
    ``'-.'``         dash-dot line style
    ``':'``          dotted line style
    =============    ===============================

    Example format strings::

        'b'    # blue markers with default shape
        'or'   # red circles
        '-g'   # green solid line
        '--'   # dashed line with default color
        '^k:'  # black triangle_up markers connected by a dotted line

    **Colors**

    The supported color abbreviations are the single letter codes

    =============    ===============================
    character        color
    =============    ===============================
    ``'b'``          blue
    ``'g'``          green
    ``'r'``          red
    ``'c'``          cyan
    ``'m'``          magenta
    ``'y'``          yellow
    ``'k'``          black
    ``'w'``          white
    =============    ===============================

    and the ``'CN'`` colors that index into the default property cycle.

    If the color is the only part of the format string, you can
    additionally use any  `matplotlib.colors` spec, e.g. full names
    (``'green'``) or hex strings (``'#008000'``).
    """
    def __init__(self,x,y,easing=None,axis=None,*args,**kwargs):
        self.mpl_obj_type = mpl.lines.Line2D
        self.mpl_plot_type = plt.plot
        super().__init__(easing=easing,axis=axis,*args, **kwargs)

        self.x = to_np_array(x)
        self.y = to_np_array(y)
        if self.x.size != self.y.size:
            raise ValueError("x and y must be the same size")

    def function(self,data_x,data_y,x,kwargs):
        if isinstance(kwargs['alpha'],np.ndarray):
            kwargs['alpha'] = kwargs['alpha'][0]
        self.obj = self.axis.plot(data_x,data_y,**kwargs)

class step(plotObject):
    """
    Make a step plot.

    Call signatures::

        step(x, y, [fmt], *, data=None, where='pre', **kwargs)
        step(x, y, [fmt], x2, y2, [fmt2], ..., *, where='pre', **kwargs)

    This is just a thin wrapper around `.plot` which changes some
    formatting options. Most of the concepts and parameters of plot can be
    used here as well.

    .. note::

        This method uses a standard plot with a step drawstyle: The *x*
        values are the reference positions and steps extend left/right/both
        directions depending on *where*.

        For the common case where you know the values and edges of the
        steps, use `~.Axes.stairs` instead.

    Parameters
    ----------
    x : array-like
        1D sequence of x positions. It is assumed, but not checked, that
        it is uniformly increasing.

    y : array-like
        1D sequence of y levels.

    fmt : str, optional
        A format string, e.g. 'g' for a green line. See `.plot` for a more
        detailed description.

        Note: While full format strings are accepted, it is recommended to
        only specify the color. Line styles are currently ignored (use
        the keyword argument *linestyle* instead). Markers are accepted
        and plotted on the given positions, however, this is a rarely
        needed feature for step plots.

    where : {'pre', 'post', 'mid'}, default: 'pre'
        Define where the steps should be placed:

        - 'pre': The y value is continued constantly to the left from
            every *x* position, i.e. the interval ``(x[i-1], x[i]]`` has the
            value ``y[i]``.
        - 'post': The y value is continued constantly to the right from
            every *x* position, i.e. the interval ``[x[i], x[i+1])`` has the
            value ``y[i]``.
        - 'mid': Steps occur half-way between the *x* positions.

    data : indexable object, optional
        An object with labelled data. If given, provide the label names to
        plot in *x* and *y*.

    **kwargs
        Additional parameters are the same as those for `.plot`.

    Returns
    -------
    list of `.Line2D`
        Objects representing the plotted data.
    """
    def __init__(self,x,y,easing=None,axis=None,*args, **kwargs):
        self.mpl_obj_type = mpl.lines.Line2D
        self.mpl_plot_type = plt.plot
        super().__init__(easing=easing,axis=axis,*args, **kwargs)

        self.x = to_np_array(x)
        self.y = to_np_array(y)
        if self.x.size != self.y.size:
            raise ValueError("x and y must be the same size")

    def function(self,data_x,data_y,x,kwargs):
        if isinstance(kwargs['alpha'],np.ndarray):
            kwargs['alpha'] = kwargs['alpha'][0]
        
        self.obj = self.axis.step(data_x,data_y,**kwargs)

class fill_between(plotObject):
    """
    Fill the area between two horizontal curves.

    The curves are defined by the points (*x*, *y1*) and (*x*,
    *y2*).  This creates one or multiple polygons describing the filled
    area.

    You may exclude some horizontal sections from filling using *where*.

    By default, the edges connect the given points directly.  Use *step*
    if the filling should be a step function, i.e. constant in between
    *x*.

    Parameters
    ----------
    x : array-like
        The x coordinates of the nodes defining the curves.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    y1 : array-like or float
        The y coordinates of the nodes defining the first curve.

    y2 : array-like or float, default: 0
        The y coordinates of the nodes defining the second curve.

    where : array-like of bool, optional
        Define *where* to exclude some horizontal regions from being filled.
        The filled regions are defined by the coordinates ``x[where]``.
        More precisely, fill between ``x[i]`` and ``x[i+1]`` if
        ``where[i] and where[i+1]``.  Note that this definition implies
        that an isolated *True* value between two *False* values in *where*
        will not result in filling.  Both sides of the *True* position
        remain unfilled due to the adjacent *False* values.

    interpolate : bool, default: False
        This option is only relevant if *where* is used and the two curves
        are crossing each other.

        Semantically, *where* is often used for *y1* > *y2* or
        similar.  By default, the nodes of the polygon defining the filled
        region will only be placed at the positions in the *x* array.
        Such a polygon cannot describe the above semantics close to the
        intersection.  The x-sections containing the intersection are
        simply clipped.

        Setting *interpolate* to *True* will calculate the actual
        intersection point and extend the filled region up to this point.

    step : {'pre', 'post', 'mid'}, optional
        Define *step* if the filling should be a step function,
        i.e. constant in between *x*.  The value determines where the
        step will occur:

        - 'pre': The y value is continued constantly to the left from
          every *x* position, i.e. the interval ``(x[i-1], x[i]]``
          has the value ``y[i]``.
        - 'post': The y value is continued constantly to the right from
          every *x* position, i.e. the interval ``[x[i], x[i+1])``
          has the value ``y[i]``.
        - 'mid': Steps occur half-way between the *x* positions.

    Returns
    -------
    `.FillBetweenPolyCollection`
        A `.FillBetweenPolyCollection` containing the plotted polygons.

    Other Parameters
    ----------------
    data : indexable object, optional
        If given, the following parameters also accept a string ``s``, which is
        interpreted as ``data[s]`` if ``s`` is a key in ``data``:

        *x*, *y1*, *y2*, *where*

    **kwargs
        All other keyword arguments are passed on to
        `.FillBetweenPolyCollection`. They control the `.Polygon` properties:

        Properties:
        agg_filter: a filter function, which takes a (m, n, 3) float array and a dpi value, and returns a (m, n, 3) array and two offsets from the bottom left corner of the image
        alpha: array-like or float or None
        animated: bool
        antialiased or aa or antialiaseds: bool or list of bools
        array: array-like or None
        capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        clim: (vmin: float, vmax: float)
        clip_box: `~matplotlib.transforms.BboxBase` or None
        clip_on: bool
        clip_path: Patch or (Path, Transform) or None
        cmap: `.Colormap` or str or None
        color: color or list of RGBA tuples
        data: array-like
        edgecolor or ec or edgecolors: color or list of color or 'face'
        facecolor or facecolors or fc: color or list of color
        figure: `~matplotlib.figure.Figure` or `~matplotlib.figure.SubFigure`
        gid: str
        hatch: {'/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*'}
        hatch_linewidth: unknown
        in_layout: bool
        joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        label: object
        linestyle or dashes or linestyles or ls: str or tuple or list thereof
        linewidth or linewidths or lw: float or list of floats
        mouseover: bool
        norm: `.Normalize` or str or None
        offset_transform or transOffset: `.Transform`
        offsets: (N, 2) or (2,) array-like
        path_effects: list of `.AbstractPathEffect`
        paths: list of array-like
        picker: None or bool or float or callable
        pickradius: float
        rasterized: bool
        sizes: `numpy.ndarray` or None
        sketch_params: (scale: float, length: float, randomness: float)
        snap: bool or None
        transform: `~matplotlib.transforms.Transform`
        url: str
        urls: list of str or None
        verts: list of array-like
        verts_and_codes: unknown
        visible: bool
        zorder: float

    See Also
    --------
    fill_between : Fill between two sets of y-values.
    fill_betweenx : Fill between two sets of x-values.

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.fill_between`.
    """
    def __init__(self,x,y1,y2,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.collections.FillBetweenPolyCollection
        self.mpl_plot_type = plt.fill_between
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = to_np_array(x)
        self.y = to_np_array(x)
        self.y1 = to_np_array(y1).reshape(-1)
        self.y2 = to_np_array(y2).reshape(-1)
        if self.y1.size != self.x.size:
            self.y1 = np.ones_like(self.x)*self.y1[0]
        if self.y2.size != self.x.size:
            self.y2 = np.ones_like(self.x)*self.y2[0]

    def clean(self,x,clear_anims=True):
        if self.obj is not None and self.base_color is None:
            self.base_color = self.obj.get_facecolor()
            if 'facecolor' not in self.kwargs:
                self.kwargs['facecolor'] = self.base_color
        super().clean(x,clear_anims)
    
    def function(self,data_x,data_y,x,kwargs):
        self.obj = self.axis.fill_between(x=data_x,**kwargs)

class fill_betweenx(plotObject):
    """
    Fill the area between two vertical curves.

    The curves are defined by the points (*y*, *x1*) and (*y*,
    *x2*).  This creates one or multiple polygons describing the filled
    area.

    You may exclude some vertical sections from filling using *where*.

    By default, the edges connect the given points directly.  Use *step*
    if the filling should be a step function, i.e. constant in between
    *y*.

    Parameters
    ----------
    y : array-like
        The y coordinates of the nodes defining the curves.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    x1 : array-like or float
        The x coordinates of the nodes defining the first curve.

    x2 : array-like or float, default: 0
        The x coordinates of the nodes defining the second curve.

    where : array-like of bool, optional
        Define *where* to exclude some vertical regions from being filled.
        The filled regions are defined by the coordinates ``y[where]``.
        More precisely, fill between ``y[i]`` and ``y[i+1]`` if
        ``where[i] and where[i+1]``.  Note that this definition implies
        that an isolated *True* value between two *False* values in *where*
        will not result in filling.  Both sides of the *True* position
        remain unfilled due to the adjacent *False* values.

    interpolate : bool, default: False
        This option is only relevant if *where* is used and the two curves
        are crossing each other.

        Semantically, *where* is often used for *x1* > *x2* or
        similar.  By default, the nodes of the polygon defining the filled
        region will only be placed at the positions in the *y* array.
        Such a polygon cannot describe the above semantics close to the
        intersection.  The y-sections containing the intersection are
        simply clipped.

        Setting *interpolate* to *True* will calculate the actual
        intersection point and extend the filled region up to this point.

    step : {'pre', 'post', 'mid'}, optional
        Define *step* if the filling should be a step function,
        i.e. constant in between *y*.  The value determines where the
        step will occur:

        - 'pre': The x value is continued constantly to the left from
          every *y* position, i.e. the interval ``(y[i-1], y[i]]``
          has the value ``x[i]``.
        - 'post': The y value is continued constantly to the right from
          every *y* position, i.e. the interval ``[y[i], y[i+1])``
          has the value ``x[i]``.
        - 'mid': Steps occur half-way between the *y* positions.

    Returns
    -------
    `.FillBetweenPolyCollection`
        A `.FillBetweenPolyCollection` containing the plotted polygons.

    Other Parameters
    ----------------
    data : indexable object, optional
        If given, the following parameters also accept a string ``s``, which is
        interpreted as ``data[s]`` if ``s`` is a key in ``data``:

        *y*, *x1*, *x2*, *where*

    **kwargs
        All other keyword arguments are passed on to
        `.FillBetweenPolyCollection`. They control the `.Polygon` properties:

        Properties:
        agg_filter: a filter function, which takes a (m, n, 3) float array and a dpi value, and returns a (m, n, 3) array and two offsets from the bottom left corner of the image
        alpha: array-like or float or None
        animated: bool
        antialiased or aa or antialiaseds: bool or list of bools
        array: array-like or None
        capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        clim: (vmin: float, vmax: float)
        clip_box: `~matplotlib.transforms.BboxBase` or None
        clip_on: bool
        clip_path: Patch or (Path, Transform) or None
        cmap: `.Colormap` or str or None
        color: color or list of RGBA tuples
        data: array-like
        edgecolor or ec or edgecolors: color or list of color or 'face'
        facecolor or facecolors or fc: color or list of color
        figure: `~matplotlib.figure.Figure` or `~matplotlib.figure.SubFigure`
        gid: str
        hatch: {'/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*'}
        hatch_linewidth: unknown
        in_layout: bool
        joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        label: object
        linestyle or dashes or linestyles or ls: str or tuple or list thereof
        linewidth or linewidths or lw: float or list of floats
        mouseover: bool
        norm: `.Normalize` or str or None
        offset_transform or transOffset: `.Transform`
        offsets: (N, 2) or (2,) array-like
        path_effects: list of `.AbstractPathEffect`
        paths: list of array-like
        picker: None or bool or float or callable
        pickradius: float
        rasterized: bool
        sizes: `numpy.ndarray` or None
        sketch_params: (scale: float, length: float, randomness: float)
        snap: bool or None
        transform: `~matplotlib.transforms.Transform`
        url: str
        urls: list of str or None
        verts: list of array-like
        verts_and_codes: unknown
        visible: bool
        zorder: float

    See Also
    --------
    fill_between : Fill between two sets of y-values.
    fill_betweenx : Fill between two sets of x-values.

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.fill_betweenx`.
    """    
    def __init__(self,y,x1,x2,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.collections.FillBetweenPolyCollection
        self.mpl_plot_type = plt.fill_betweenx
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = to_np_array(y)
        self.y = to_np_array(y)
        self.x1 = to_np_array(x1).reshape(-1)
        self.x2 = to_np_array(x2).reshape(-1)
        if self.x1.size != self.y.size:
            self.x1 = np.ones_like(self.y)*self.x1[0]
        if self.x2.size != self.y.size:
            self.x2 = np.ones_like(self.y)*self.x2[0]

    def clean(self,x,clear_anims=True):
        if self.obj is not None and self.base_color is None:
            self.base_color = self.obj.get_facecolor()
            if 'facecolor' not in self.kwargs:
                self.kwargs['facecolor'] = self.base_color
        super().clean(x,clear_anims)
    
    def function(self,data_x,data_y,x,kwargs):
        self.obj = self.axis.fill_betweenx(y=data_x,**kwargs)
    
class axvline(plotObject):
    """
    Add a vertical line spanning the whole or fraction of the Axes.

    Note: If you want to set y-limits in data coordinates, use
    `~.Axes.vlines` instead.

    Parameters
    ----------
    x : float, default: 0
        x position in :ref:`data coordinates <coordinate-systems>`.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    ymin : float, default: 0
        The start y-position in :ref:`axes coordinates <coordinate-systems>`.
        Should be between 0 and 1, 0 being the bottom of the plot, 1 the
        top of the plot.

    ymax : float, default: 1
        The end y-position in :ref:`axes coordinates <coordinate-systems>`.
        Should be between 0 and 1, 0 being the bottom of the plot, 1 the
        top of the plot.

    Returns
    -------
    `~matplotlib.lines.Line2D`
        A `.Line2D` specified via two points ``(x, ymin)``, ``(x, ymax)``.
        Its transform is set such that *x* is in
        :ref:`data coordinates <coordinate-systems>` and *y* is in
        :ref:`axes coordinates <coordinate-systems>`.

        This is still a generic line and the vertical character is only
        realized through using identical *x* values for both points. Thus,
        if you want to change the *x* value later, you have to provide two
        values ``line.set_xdata([3, 3])``.

    Other Parameters
    ----------------
    **kwargs
        Valid keyword arguments are `.Line2D` properties, except for
        'transform':

        Properties:
        agg_filter: a filter function, which takes a (m, n, 3) float array and a dpi value, and returns a (m, n, 3) array and two offsets from the bottom left corner of the image
        alpha: float or None
        animated: bool
        antialiased or aa: bool
        clip_box: `~matplotlib.transforms.BboxBase` or None
        clip_on: bool
        clip_path: Patch or (Path, Transform) or None
        color or c: color
        dash_capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        dash_joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        dashes: sequence of floats (on/off ink in points) or (None, None)
        data: (2, N) array or two 1D arrays
        drawstyle or ds: {'default', 'steps', 'steps-pre', 'steps-mid', 'steps-post'}, default: 'default'
        figure: `~matplotlib.figure.Figure` or `~matplotlib.figure.SubFigure`
        fillstyle: {'full', 'left', 'right', 'bottom', 'top', 'none'}
        gapcolor: color or None
        gid: str
        in_layout: bool
        label: object
        linestyle or ls: {'-', '--', '-.', ':', '', (offset, on-off-seq), ...}
        linewidth or lw: float
        marker: marker style string, `~.path.Path` or `~.markers.MarkerStyle`
        markeredgecolor or mec: color
        markeredgewidth or mew: float
        markerfacecolor or mfc: color
        markerfacecoloralt or mfcalt: color
        markersize or ms: float
        markevery: None or int or (int, int) or slice or list[int] or float or (float, float) or list[bool]
        mouseover: bool
        path_effects: list of `.AbstractPathEffect`
        picker: float or callable[[Artist, Event], tuple[bool, dict]]
        pickradius: float
        rasterized: bool
        sketch_params: (scale: float, length: float, randomness: float)
        snap: bool or None
        solid_capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        solid_joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        transform: unknown
        url: str
        visible: bool
        xdata: 1D array
        ydata: 1D array
        zorder: float

    See Also
    --------
    vlines : Add vertical lines in data coordinates.
    axvspan : Add a vertical span (rectangle) across the axis.
    axline : Add a line with an arbitrary slope.

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.axvline`.

    Examples
    --------
    * draw a thick red vline at *x* = 0 that spans the yrange::

        >>> axvline(linewidth=4, color='r')

    * draw a default vline at *x* = 1 that spans the yrange::

        >>> axvline(x=1)

    * draw a default vline at *x* = .5 that spans the middle half of
      the yrange::

        >>> axvline(x=.5, ymin=0.25, ymax=0.75)
    """
    def __init__(self, x,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.lines.Line2D
        self.mpl_plot_type = plt.axvline
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = x
    
    def function(self,data_x,data_y,x,kwargs):
        if 'ymax' in kwargs:
            kwargs['ymax'] = kwargs['ymax'][0]
        if 'ymin' in kwargs:
            kwargs['ymin'] = kwargs['ymin'][0]

        if len(data_x) > 0:
            self.obj = [self.axis.axvline(data_x,**kwargs)]

class axhline(plotObject):
    """
    Add a horizontal line spanning the whole or fraction of the Axes.

    Note: If you want to set x-limits in data coordinates, use
    `~.Axes.hlines` instead.

    Parameters
    ----------
    y : float, default: 0
        y position in :ref:`data coordinates <coordinate-systems>`.

    xmin : float, default: 0
        The start x-position in :ref:`axes coordinates <coordinate-systems>`.
        Should be between 0 and 1, 0 being the far left of the plot,
        1 the far right of the plot.

    xmax : float, default: 1
        The end x-position in :ref:`axes coordinates <coordinate-systems>`.
        Should be between 0 and 1, 0 being the far left of the plot,
        1 the far right of the plot.

    Returns
    -------
    `~matplotlib.lines.Line2D`
        A `.Line2D` specified via two points ``(xmin, y)``, ``(xmax, y)``.
        Its transform is set such that *x* is in
        :ref:`axes coordinates <coordinate-systems>` and *y* is in
        :ref:`data coordinates <coordinate-systems>`.

        This is still a generic line and the horizontal character is only
        realized through using identical *y* values for both points. Thus,
        if you want to change the *y* value later, you have to provide two
        values ``line.set_ydata([3, 3])``.

    Other Parameters
    ----------------
    **kwargs
        Valid keyword arguments are `.Line2D` properties, except for
        'transform':

        %(Line2D:kwdoc)s

    See Also
    --------
    hlines : Add horizontal lines in data coordinates.
    axhspan : Add a horizontal span (rectangle) across the axis.
    axline : Add a line with an arbitrary slope.

    Examples
    --------
    * draw a thick red hline at 'y' = 0 that spans the xrange::

        >>> axhline(linewidth=4, color='r')

    * draw a default hline at 'y' = 1 that spans the xrange::

        >>> axhline(y=1)

    * draw a default hline at 'y' = .5 that spans the middle half of
        the xrange::

        >>> axhline(y=.5, xmin=0.25, xmax=0.75)
    """
    def __init__(self, y,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.lines.Line2D
        self.mpl_plot_type = plt.axvline
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = y
    
    def function(self,data_x,data_y,x,kwargs):
        if 'xmax' in kwargs:
            kwargs['xmax'] = kwargs['xmax'][0]
        if 'xmin' in kwargs:
            kwargs['xmin'] = kwargs['xmin'][0]
        if len(data_x) > 0:
            self.obj = [self.axis.axhline(data_x,**kwargs)]

class errorbar(plotObject):
    """
    Plot y versus x as lines and/or markers with attached errorbars.

    *x*, *y* define the data locations, *xerr*, *yerr* define the errorbar
    sizes. By default, this draws the data markers/lines as well as the
    errorbars. Use fmt='none' to draw errorbars without any data markers.

    .. versionadded:: 3.7
       Caps and error lines are drawn in polar coordinates on polar plots.


    Parameters
    ----------
    x, y : float or array-like
        The data positions.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    xerr, yerr : float or array-like, shape(N,) or shape(2, N), optional
        The errorbar sizes:

        - scalar: Symmetric +/- values for all data points.
        - shape(N,): Symmetric +/-values for each data point.
        - shape(2, N): Separate - and + values for each bar. First row
          contains the lower errors, the second row contains the upper
          errors.
        - *None*: No errorbar.

        All values must be >= 0.

    fmt : str, default: ''
        The format for the data points / data lines. See `.plot` for
        details.

        Use 'none' (case-insensitive) to plot errorbars without any data
        markers.

    ecolor : color, default: None
        The color of the errorbar lines.  If None, use the color of the
        line connecting the markers.

    elinewidth : float, default: None
        The linewidth of the errorbar lines. If None, the linewidth of
        the current style is used.

    capsize : float, default: errorbar.capsize
        The length of the error bar caps in points.

    capthick : float, default: None
        An alias to the keyword argument *markeredgewidth* (a.k.a. *mew*).
        This setting is a more sensible name for the property that
        controls the thickness of the error bar cap in points. For
        backwards compatibility, if *mew* or *markeredgewidth* are given,
        then they will over-ride *capthick*. This may change in future
        releases.

    barsabove : bool, default: False
        If True, will plot the errorbars above the plot
        symbols. Default is below.

    lolims, uplims, xlolims, xuplims : bool or array-like, default: False
        These arguments can be used to indicate that a value gives only
        upper/lower limits.  In that case a caret symbol is used to
        indicate this. *lims*-arguments may be scalars, or array-likes of
        the same length as *xerr* and *yerr*.  To use limits with inverted
        axes, `~.Axes.set_xlim` or `~.Axes.set_ylim` must be called before
        :meth:`errorbar`.  Note the tricky parameter names: setting e.g.
        *lolims* to True means that the y-value is a *lower* limit of the
        True value, so, only an *upward*-pointing arrow will be drawn!

    errorevery : int or (int, int), default: 1
        draws error bars on a subset of the data. *errorevery* =N draws
        error bars on the points (x[::N], y[::N]).
        *errorevery* =(start, N) draws error bars on the points
        (x[start::N], y[start::N]). e.g. errorevery=(6, 3)
        adds error bars to the data at (x[6], x[9], x[12], x[15], ...).
        Used to avoid overlapping error bars when two series share x-axis
        values.

    Returns
    -------
    `.ErrorbarContainer`
        The container contains:

        - data_line : A `~matplotlib.lines.Line2D` instance of x, y plot markers
          and/or line.
        - caplines : A tuple of `~matplotlib.lines.Line2D` instances of the error
          bar caps.
        - barlinecols : A tuple of `.LineCollection` with the horizontal and
          vertical error ranges.

    Other Parameters
    ----------------
    data : indexable object, optional
        If given, the following parameters also accept a string ``s``, which is
        interpreted as ``data[s]`` if ``s`` is a key in ``data``:

        *x*, *y*, *xerr*, *yerr*

    **kwargs
        All other keyword arguments are passed on to the `~.Axes.plot` call
        drawing the markers. For example, this code makes big red squares
        with thick green edges::

            x, y, yerr = rand(3, 10)
            errorbar(x, y, yerr, marker='s', mfc='red',
                     mec='green', ms=20, mew=4)

        where *mfc*, *mec*, *ms* and *mew* are aliases for the longer
        property names, *markerfacecolor*, *markeredgecolor*, *markersize*
        and *markeredgewidth*.

        Valid kwargs for the marker properties are:

        - *dashes*
        - *dash_capstyle*
        - *dash_joinstyle*
        - *drawstyle*
        - *fillstyle*
        - *linestyle*
        - *marker*
        - *markeredgecolor*
        - *markeredgewidth*
        - *markerfacecolor*
        - *markerfacecoloralt*
        - *markersize*
        - *markevery*
        - *solid_capstyle*
        - *solid_joinstyle*

        Refer to the corresponding `.Line2D` property for more details:

        Properties:
        agg_filter: a filter function, which takes a (m, n, 3) float array and a dpi value, and returns a (m, n, 3) array and two offsets from the bottom left corner of the image
        alpha: float or None
        animated: bool
        antialiased or aa: bool
        clip_box: `~matplotlib.transforms.BboxBase` or None
        clip_on: bool
        clip_path: Patch or (Path, Transform) or None
        color or c: color
        dash_capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        dash_joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        dashes: sequence of floats (on/off ink in points) or (None, None)
        data: (2, N) array or two 1D arrays
        drawstyle or ds: {'default', 'steps', 'steps-pre', 'steps-mid', 'steps-post'}, default: 'default'
        figure: `~matplotlib.figure.Figure` or `~matplotlib.figure.SubFigure`
        fillstyle: {'full', 'left', 'right', 'bottom', 'top', 'none'}
        gapcolor: color or None
        gid: str
        in_layout: bool
        label: object
        linestyle or ls: {'-', '--', '-.', ':', '', (offset, on-off-seq), ...}
        linewidth or lw: float
        marker: marker style string, `~.path.Path` or `~.markers.MarkerStyle`
        markeredgecolor or mec: color
        markeredgewidth or mew: float
        markerfacecolor or mfc: color
        markerfacecoloralt or mfcalt: color
        markersize or ms: float
        markevery: None or int or (int, int) or slice or list[int] or float or (float, float) or list[bool]
        mouseover: bool
        path_effects: list of `.AbstractPathEffect`
        picker: float or callable[[Artist, Event], tuple[bool, dict]]
        pickradius: float
        rasterized: bool
        sketch_params: (scale: float, length: float, randomness: float)
        snap: bool or None
        solid_capstyle: `.CapStyle` or {'butt', 'projecting', 'round'}
        solid_joinstyle: `.JoinStyle` or {'miter', 'round', 'bevel'}
        transform: unknown
        url: str
        visible: bool
        xdata: 1D array
        ydata: 1D array
        zorder: float

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.errorbar`.
    """
    def __init__(self,x,y,xerr=None,yerr=None,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.lines.Line2D
        self.mpl_plot_type = plt.axvline
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = x
        self.y = y
        if xerr is None:
            xerr = np.zeros_like(x)
        if yerr is None:
            yerr = np.zeros_like(y)
        self.xerr = xerr
        self.yerr = yerr

    def morph(self,new_x,new_y,duration,new_xerr=None,new_yerr=None,delay=0,easing=None,persistent=True):
        if new_xerr is None:
            new_xerr = self.xerr
        if new_yerr is None:
            new_yerr = self.yerr
        if isinstance(new_x,numbers.Number):
            new_x = [new_x]
            new_y = [new_y]
            new_xerr = [new_xerr]
            new_yerr = [new_yerr]
        
        self.anims.append({
            'name':'morph',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'new_x':new_x,
            'new_y':new_y,
            'new_x_err':new_xerr,
            'new_y_err':new_yerr,
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self
    
    def function(self,data_x,data_y,x,kwargs):
        obj = self.axis.errorbar(data_x,data_y,**kwargs)
        obj = [obj.lines[0]] + list(obj.lines[1]) + list(obj.lines[2])
        self.obj = obj

class hist(plotObject):
    """
    Compute and plot a histogram.

    This method uses `numpy.histogram` to bin the data in *x* and count the
    number of values in each bin, then draws the distribution either as a
    `.BarContainer` or `.Polygon`. The *bins*, *range*, *density*, and
    *weights* parameters are forwarded to `numpy.histogram`.

    If the data has already been binned and counted, use `~.bar` or
    `~.stairs` to plot the distribution::

        counts, bins = np.histogram(x)
        plt.stairs(counts, bins)

    Alternatively, plot pre-computed bins and counts using ``hist()`` by
    treating each bin as a single point with a weight equal to its count::

        plt.hist(bins[:-1], bins, weights=counts)

    The data input *x* can be a singular array, a list of datasets of
    potentially different lengths ([*x0*, *x1*, ...]), or a 2D ndarray in
    which each column is a dataset. Note that the ndarray form is
    transposed relative to the list form. If the input is an array, then
    the return value is a tuple (*n*, *bins*, *patches*); if the input is a
    sequence of arrays, then the return value is a tuple
    ([*n0*, *n1*, ...], *bins*, [*patches0*, *patches1*, ...]).

    Masked arrays are not supported.

    Parameters
    ----------
    x : (n,) array or sequence of (n,) arrays
        Input values, this takes either a single array or a sequence of
        arrays which are not required to be of the same length.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    bins : int or sequence or str, default: hist.bins
        If *bins* is an integer, it defines the number of equal-width bins
        in the range.

        If *bins* is a sequence, it defines the bin edges, including the
        left edge of the first bin and the right edge of the last bin;
        in this case, bins may be unequally spaced.  All but the last
        (righthand-most) bin is half-open.  In other words, if *bins* is::

            [1, 2, 3, 4]

        then the first bin is ``[1, 2)`` (including 1, but excluding 2) and
        the second ``[2, 3)``.  The last bin, however, is ``[3, 4]``, which
        *includes* 4.

        If *bins* is a string, it is one of the binning strategies
        supported by `numpy.histogram_bin_edges`: 'auto', 'fd', 'doane',
        'scott', 'stone', 'rice', 'sturges', or 'sqrt'.

    range : tuple or None, default: None
        The lower and upper range of the bins. Lower and upper outliers
        are ignored. If not provided, *range* is ``(x.min(), x.max())``.
        Range has no effect if *bins* is a sequence.

        If *bins* is a sequence or *range* is specified, autoscaling
        is based on the specified bin range instead of the
        range of x.

    density : bool, default: False
        If ``True``, draw and return a probability density: each bin
        will display the bin's raw count divided by the total number of
        counts *and the bin width*
        (``density = counts / (sum(counts) * np.diff(bins))``),
        so that the area under the histogram integrates to 1
        (``np.sum(density * np.diff(bins)) == 1``).

        If *stacked* is also ``True``, the sum of the histograms is
        normalized to 1.

    weights : (n,) array-like or None, default: None
        An array of weights, of the same shape as *x*.  Each value in
        *x* only contributes its associated weight towards the bin count
        (instead of 1).  If *density* is ``True``, the weights are
        normalized, so that the integral of the density over the range
        remains 1.

    cumulative : bool or -1, default: False
        If ``True``, then a histogram is computed where each bin gives the
        counts in that bin plus all bins for smaller values. The last bin
        gives the total number of datapoints.

        If *density* is also ``True`` then the histogram is normalized such
        that the last bin equals 1.

        If *cumulative* is a number less than 0 (e.g., -1), the direction
        of accumulation is reversed.  In this case, if *density* is also
        ``True``, then the histogram is normalized such that the first bin
        equals 1.

    bottom : array-like or float, default: 0
        Location of the bottom of each bin, i.e. bins are drawn from
        ``bottom`` to ``bottom + hist(x, bins)`` If a scalar, the bottom
        of each bin is shifted by the same amount. If an array, each bin
        is shifted independently and the length of bottom must match the
        number of bins. If None, defaults to 0.

    histtype : {'bar', 'barstacked', 'step', 'stepfilled'}, default: 'bar'
        The type of histogram to draw.

        - 'bar' is a traditional bar-type histogram.  If multiple data
          are given the bars are arranged side by side.
        - 'barstacked' is a bar-type histogram where multiple
          data are stacked on top of each other.
        - 'step' generates a lineplot that is by default unfilled.
        - 'stepfilled' generates a lineplot that is by default filled.

    align : {'left', 'mid', 'right'}, default: 'mid'
        The horizontal alignment of the histogram bars.

        - 'left': bars are centered on the left bin edges.
        - 'mid': bars are centered between the bin edges.
        - 'right': bars are centered on the right bin edges.

    orientation : {'vertical', 'horizontal'}, default: 'vertical'
        If 'horizontal', `~.Axes.barh` will be used for bar-type histograms
        and the *bottom* kwarg will be the left edges.

    rwidth : float or None, default: None
        The relative width of the bars as a fraction of the bin width.  If
        ``None``, automatically compute the width.

        Ignored if *histtype* is 'step' or 'stepfilled'.

    log : bool, default: False
        If ``True``, the histogram axis will be set to a log scale.

    color : color or list of color or None, default: None
        Color or sequence of colors, one per dataset.  Default (``None``)
        uses the standard line color sequence.

    label : str or list of str, optional
        String, or sequence of strings to match multiple datasets.  Bar
        charts yield multiple patches per dataset, but only the first gets
        the label, so that `~.Axes.legend` will work as expected.

    stacked : bool, default: False
        If ``True``, multiple data are stacked on top of each other If
        ``False`` multiple data are arranged side by side if histtype is
        'bar' or on top of each other if histtype is 'step'

    Returns
    -------
    n : array or list of arrays
        The values of the histogram bins. See *density* and *weights* for a
        description of the possible semantics.  If input *x* is an array,
        then this is an array of length *nbins*. If input is a sequence of
        arrays ``[data1, data2, ...]``, then this is a list of arrays with
        the values of the histograms for each of the arrays in the same
        order.  The dtype of the array *n* (or of its element arrays) will
        always be float even if no weighting or normalization is used.

    bins : array
        The edges of the bins. Length nbins + 1 (nbins left edges and right
        edge of last bin).  Always a single array even when multiple data
        sets are passed in.

    patches : `.BarContainer` or list of a single `.Polygon` or list of such objects
        Container of individual artists used to create the histogram
        or list of such containers if there are multiple input datasets.

    Other Parameters
    ----------------
    data : indexable object, optional
        If given, the following parameters also accept a string ``s``, which is
        interpreted as ``data[s]`` if ``s`` is a key in ``data``:

        *x*, *weights*

    **kwargs
        `~matplotlib.patches.Patch` properties. The following properties
        additionally accept a sequence of values corresponding to the
        datasets in *x*:
        *edgecolor*, *facecolor*, *linewidth*, *linestyle*, *hatch*.

        .. versionadded:: 3.10
           Allowing sequences of values in above listed Patch properties.

    See Also
    --------
    hist2d : 2D histogram with rectangular bins
    hexbin : 2D histogram with hexagonal bins
    stairs : Plot a pre-computed histogram
    bar : Plot a pre-computed histogram

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.hist`.

    For large numbers of bins (>1000), plotting can be significantly
    accelerated by using `~.Axes.stairs` to plot a pre-computed histogram
    (``plt.stairs(*np.histogram(data))``), or by setting *histtype* to
    'step' or 'stepfilled' rather than 'bar' or 'barstacked'.
    """
    def __init__(self,x,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.patches.Rectangle
        self.mpl_plot_type = plt.hist
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = to_np_array(x)
        self.y = np.zeros_like(self.x)

    def clean(self,x,clear_anims=True):
        if self.obj is not None and self.base_color is None:
            self.base_color = self.obj[0].get_facecolor()
            if 'color' not in self.kwargs:
                self.kwargs['color'] = self.base_color
        super().clean(x,clear_anims)
    
    def morph(self,new_x,duration,delay=0,easing=None,persistent=True,**kwargs):
        if isinstance(new_x,numbers.Number):
            new_x = [new_x]
        
        self.anims.append({
            'name':'morph',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'new_x':new_x,
            'new_y':np.zeros_like(self.y),
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self

    def function(self,data_x,data_y,x,kwargs):
        if isinstance(kwargs['alpha'],np.ndarray):
            kwargs['alpha'] = kwargs['alpha'][0]
        
        if 'bins' in kwargs:
            kwargs['bins'] = to_np_array(kwargs['bins'])

        if 'bins' in kwargs and len(kwargs['bins']) == 1:
            kwargs['bins'] = int(kwargs['bins'][0])
        
        h,edges,self.obj = self.axis.hist(data_x,**kwargs)

class hist2d(plotObject):
    """
    Make a 2D histogram plot.

    Parameters
    ----------
    x, y : array-like, shape (n, )
        Input values

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    bins : None or int or [int, int] or array-like or [array, array]

        The bin specification:

        - If int, the number of bins for the two dimensions
          (``nx = ny = bins``).
        - If ``[int, int]``, the number of bins in each dimension
          (``nx, ny = bins``).
        - If array-like, the bin edges for the two dimensions
          (``x_edges = y_edges = bins``).
        - If ``[array, array]``, the bin edges in each dimension
          (``x_edges, y_edges = bins``).

        The default value is 10.

    range : array-like shape(2, 2), optional
        The leftmost and rightmost edges of the bins along each dimension
        (if not specified explicitly in the bins parameters): ``[[xmin,
        xmax], [ymin, ymax]]``. All values outside of this range will be
        considered outliers and not tallied in the histogram.

    density : bool, default: False
        Normalize histogram.  See the documentation for the *density*
        parameter of `~.Axes.hist` for more details.

    weights : array-like, shape (n, ), optional
        An array of values w_i weighing each sample (x_i, y_i).

    cmin, cmax : float, default: None
        All bins that has count less than *cmin* or more than *cmax* will not be
        displayed (set to NaN before passing to `~.Axes.pcolormesh`) and these count
        values in the return value count histogram will also be set to nan upon
        return.

    Returns
    -------
    h : 2D array
        The bi-dimensional histogram of samples x and y. Values in x are
        histogrammed along the first dimension and values in y are
        histogrammed along the second dimension.
    xedges : 1D array
        The bin edges along the x-axis.
    yedges : 1D array
        The bin edges along the y-axis.
    image : `~.matplotlib.collections.QuadMesh`

    Other Parameters
    ----------------
    cmap : str or `~matplotlib.colors.Colormap`, default: image.cmap
        The Colormap instance or registered colormap name used to map scalar data
        to colors.

    norm : str or `~matplotlib.colors.Normalize`, optional
        The normalization method used to scale scalar data to the [0, 1] range
        before mapping to colors using *cmap*. By default, a linear scaling is
        used, mapping the lowest value to 0 and the highest to 1.

        If given, this can be one of the following:

        - An instance of `.Normalize` or one of its subclasses
          (see :ref:`colormapnorms`).
        - A scale name, i.e. one of "linear", "log", "symlog", "logit", etc.  For a
          list of available scales, call `matplotlib.scale.get_scale_names()`.
          In that case, a suitable `.Normalize` subclass is dynamically generated
          and instantiated.

    vmin, vmax : float, optional
        When using scalar data and no explicit *norm*, *vmin* and *vmax* define
        the data range that the colormap covers. By default, the colormap covers
        the complete value range of the supplied data. It is an error to use
        *vmin*/*vmax* when a *norm* instance is given (but using a `str` *norm*
        name together with *vmin*/*vmax* is acceptable).

    colorizer : `~matplotlib.colorizer.Colorizer` or None, default: None
        The Colorizer object used to map color to data. If None, a Colorizer
        object is created from a *norm* and *cmap*.

    alpha : ``0 <= scalar <= 1`` or ``None``, optional
        The alpha blending value.

    data : indexable object, optional
        If given, the following parameters also accept a string ``s``, which is
        interpreted as ``data[s]`` if ``s`` is a key in ``data``:

        *x*, *y*, *weights*

    **kwargs
        Additional parameters are passed along to the
        `~.Axes.pcolormesh` method and `~matplotlib.collections.QuadMesh`
        constructor.

    See Also
    --------
    hist : 1D histogram plotting
    hexbin : 2D histogram with hexagonal bins

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.hist2d`.

    - Currently ``hist2d`` calculates its own axis limits, and any limits
      previously set are ignored.
    - Rendering the histogram with a logarithmic color scale is
      accomplished by passing a `.colors.LogNorm` instance to the *norm*
      keyword argument. Likewise, power-law normalization (similar
      in effect to gamma correction) can be accomplished with
      `.colors.PowerNorm`.
    """
    def __init__(self,x,y,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.collections.QuadMesh
        self.mpl_plot_type = plt.hist2d
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = to_np_array(x)
        self.y = to_np_array(y)
    
    def function(self,data_x,data_y,x,kwargs):
        if isinstance(kwargs['alpha'],np.ndarray):
            kwargs['alpha'] = kwargs['alpha'][0]
        
        if 'bins' in kwargs:
            kwargs['bins'] = to_np_array(kwargs['bins'])

        if 'bins' in kwargs and len(kwargs['bins']) == 1:
            kwargs['bins'] = int(kwargs['bins'][0])
        
        if 'color' in kwargs:
            kwargs.pop('color')

        data_x = np.array(data_x).flatten()
        data_y = np.array(data_y).flatten()

        #Have to reset xlim and ylim because hist2d does not respect the imposed limits
        old_xlim = self.axis.get_xlim()
        old_ylim = self.axis.get_ylim()
        h,xedges,yedges,self.obj = self.axis.hist2d(data_x,data_y,**kwargs)
        self.axis.set_xlim(old_xlim)
        self.axis.set_ylim(old_ylim)

class contourf(plotObject):
    """
    Plot filled contours.

    Call signature::

        contourf([X, Y,] Z, /, [levels], **kwargs)

    The arguments *X*, *Y*, *Z* are positional-only.

    `.contour` and `.contourf` draw contour lines and filled contours,
    respectively.  Except as noted, function signatures and return values
    are the same for both versions.

    Parameters
    ----------
    X, Y : array-like, optional
        The coordinates of the values in *Z*.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


        *X* and *Y* must both be 2D with the same shape as *Z* (e.g.
        created via `numpy.meshgrid`), or they must both be 1-D such
        that ``len(X) == N`` is the number of columns in *Z* and
        ``len(Y) == M`` is the number of rows in *Z*.

        *X* and *Y* must both be ordered monotonically.

        If not given, they are assumed to be integer indices, i.e.
        ``X = range(N)``, ``Y = range(M)``.

    Z : (M, N) array-like
        The height values over which the contour is drawn.  Color-mapping is
        controlled by *cmap*, *norm*, *vmin*, and *vmax*.

    levels : int or array-like, optional
        Determines the number and positions of the contour lines / regions.

        If an int *n*, use `~matplotlib.ticker.MaxNLocator`, which tries
        to automatically choose no more than *n+1* "nice" contour levels
        between minimum and maximum numeric values of *Z*.

        If array-like, draw contour lines at the specified levels.
        The values must be in increasing order.

    Returns
    -------
    `~.contour.QuadContourSet`

    Other Parameters
    ----------------
    corner_mask : bool, default: contour.corner_mask
        Enable/disable corner masking, which only has an effect if *Z* is
        a masked array.  If ``False``, any quad touching a masked point is
        masked out.  If ``True``, only the triangular corners of quads
        nearest those points are always masked out, other triangular
        corners comprising three unmasked points are contoured as usual.

    colors : color or list of color, optional
        The colors of the levels, i.e. the lines for `.contour` and the
        areas for `.contourf`.

        The sequence is cycled for the levels in ascending order. If the
        sequence is shorter than the number of levels, it's repeated.

        As a shortcut, a single color may be used in place of one-element lists, i.e.
        ``'red'`` instead of ``['red']`` to color all levels with the same color.

        .. versionchanged:: 3.10
            Previously a single color had to be expressed as a string, but now any
            valid color format may be passed.

        By default (value *None*), the colormap specified by *cmap*
        will be used.

    alpha : float, default: 1
        The alpha blending value, between 0 (transparent) and 1 (opaque).

    cmap : str or `~matplotlib.colors.Colormap`, default: image.cmap
        The Colormap instance or registered colormap name used to map scalar data
        to colors.

        This parameter is ignored if *colors* is set.

    norm : str or `~matplotlib.colors.Normalize`, optional
        The normalization method used to scale scalar data to the [0, 1] range
        before mapping to colors using *cmap*. By default, a linear scaling is
        used, mapping the lowest value to 0 and the highest to 1.

        If given, this can be one of the following:

        - An instance of `.Normalize` or one of its subclasses
          (see :ref:`colormapnorms`).
        - A scale name, i.e. one of "linear", "log", "symlog", "logit", etc.  For a
          list of available scales, call `matplotlib.scale.get_scale_names()`.
          In that case, a suitable `.Normalize` subclass is dynamically generated
          and instantiated.

        This parameter is ignored if *colors* is set.

    vmin, vmax : float, optional
        When using scalar data and no explicit *norm*, *vmin* and *vmax* define
        the data range that the colormap covers. By default, the colormap covers
        the complete value range of the supplied data. It is an error to use
        *vmin*/*vmax* when a *norm* instance is given (but using a `str` *norm*
        name together with *vmin*/*vmax* is acceptable).

        If *vmin* or *vmax* are not given, the default color scaling is based on
        *levels*.

        This parameter is ignored if *colors* is set.

    colorizer : `~matplotlib.colorizer.Colorizer` or None, default: None
        The Colorizer object used to map color to data. If None, a Colorizer
        object is created from a *norm* and *cmap*.

        This parameter is ignored if *colors* is set.

    origin : {*None*, 'upper', 'lower', 'image'}, default: None
        Determines the orientation and exact position of *Z* by specifying
        the position of ``Z[0, 0]``.  This is only relevant, if *X*, *Y*
        are not given.

        - *None*: ``Z[0, 0]`` is at X=0, Y=0 in the lower left corner.
        - 'lower': ``Z[0, 0]`` is at X=0.5, Y=0.5 in the lower left corner.
        - 'upper': ``Z[0, 0]`` is at X=N+0.5, Y=0.5 in the upper left
          corner.
        - 'image': Use the value from image.origin.

    extent : (x0, x1, y0, y1), optional
        If *origin* is not *None*, then *extent* is interpreted as in
        `.imshow`: it gives the outer pixel boundaries. In this case, the
        position of Z[0, 0] is the center of the pixel, not a corner. If
        *origin* is *None*, then (*x0*, *y0*) is the position of Z[0, 0],
        and (*x1*, *y1*) is the position of Z[-1, -1].

        This argument is ignored if *X* and *Y* are specified in the call
        to contour.

    locator : ticker.Locator subclass, optional
        The locator is used to determine the contour levels if they
        are not given explicitly via *levels*.
        Defaults to `~.ticker.MaxNLocator`.

    extend : {'neither', 'both', 'min', 'max'}, default: 'neither'
        Determines the ``contourf``-coloring of values that are outside the
        *levels* range.

        If 'neither', values outside the *levels* range are not colored.
        If 'min', 'max' or 'both', color the values below, above or below
        and above the *levels* range.

        Values below ``min(levels)`` and above ``max(levels)`` are mapped
        to the under/over values of the `.Colormap`. Note that most
        colormaps do not have dedicated colors for these by default, so
        that the over and under values are the edge values of the colormap.
        You may want to set these values explicitly using
        `.Colormap.set_under` and `.Colormap.set_over`.

        .. note::

            An existing `.QuadContourSet` does not get notified if
            properties of its colormap are changed. Therefore, an explicit
            call `~.ContourSet.changed()` is needed after modifying the
            colormap. The explicit call can be left out, if a colorbar is
            assigned to the `.QuadContourSet` because it internally calls
            `~.ContourSet.changed()`.

        Example::

            x = np.arange(1, 10)
            y = x.reshape(-1, 1)
            h = x * y

            cs = plt.contourf(h, levels=[10, 30, 50],
                colors=['#808080', '#A0A0A0', '#C0C0C0'], extend='both')
            cs.cmap.set_over('red')
            cs.cmap.set_under('blue')
            cs.changed()

    xunits, yunits : registered units, optional
        Override axis units by specifying an instance of a
        :class:`matplotlib.units.ConversionInterface`.

    antialiased : bool, optional
        Enable antialiasing, overriding the defaults.  For
        filled contours, the default is *False*.  For line contours,
        it is taken from lines.antialiased.

    nchunk : int >= 0, optional
        If 0, no subdivision of the domain.  Specify a positive integer to
        divide the domain into subdomains of *nchunk* by *nchunk* quads.
        Chunking reduces the maximum length of polygons generated by the
        contouring algorithm which reduces the rendering workload passed
        on to the backend and also requires slightly less RAM.  It can
        however introduce rendering artifacts at chunk boundaries depending
        on the backend, the *antialiased* flag and value of *alpha*.

    linewidths : float or array-like, default: contour.linewidth
        *Only applies to* `.contour`.

        The line width of the contour lines.

        If a number, all levels will be plotted with this linewidth.

        If a sequence, the levels in ascending order will be plotted with
        the linewidths in the order specified.

        If None, this falls back to lines.linewidth.

    linestyles : {*None*, 'solid', 'dashed', 'dashdot', 'dotted'}, optional
        *Only applies to* `.contour`.

        If *linestyles* is *None*, the default is 'solid' unless the lines are
        monochrome. In that case, negative contours will instead take their
        linestyle from the *negative_linestyles* argument.

        *linestyles* can also be an iterable of the above strings specifying a set
        of linestyles to be used. If this iterable is shorter than the number of
        contour levels it will be repeated as necessary.

    negative_linestyles : {*None*, 'solid', 'dashed', 'dashdot', 'dotted'},                        optional
        *Only applies to* `.contour`.

        If *linestyles* is *None* and the lines are monochrome, this argument
        specifies the line style for negative contours.

        If *negative_linestyles* is *None*, the default is taken from
        contour.negative_linestyle.

        *negative_linestyles* can also be an iterable of the above strings
        specifying a set of linestyles to be used. If this iterable is shorter than
        the number of contour levels it will be repeated as necessary.

    hatches : list[str], optional
        *Only applies to* `.contourf`.

        A list of cross hatch patterns to use on the filled areas.
        If None, no hatching will be added to the contour.

    algorithm : {'mpl2005', 'mpl2014', 'serial', 'threaded'}, optional
        Which contouring algorithm to use to calculate the contour lines and
        polygons. The algorithms are implemented in
        `ContourPy <https://github.com/contourpy/contourpy>`_, consult the
        `ContourPy documentation <https://contourpy.readthedocs.io>`_ for
        further information.

        The default is taken from contour.algorithm.

    clip_path : `~matplotlib.patches.Patch` or `.Path` or `.TransformedPath`
        Set the clip path.  See `~matplotlib.artist.Artist.set_clip_path`.

        .. versionadded:: 3.8

    data : indexable object, optional
        If given, all parameters also accept a string ``s``, which is
        interpreted as ``data[s]`` if ``s`` is a key in ``data``.

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.contourf`.

    1. `.contourf` differs from the MATLAB version in that it does not draw
       the polygon edges. To draw edges, add line contours with calls to
       `.contour`.

    2. `.contourf` fills intervals that are closed at the top; that is, for
       boundaries *z1* and *z2*, the filled region is::

          z1 < Z <= z2

       except for the lowest interval, which is closed on both sides (i.e.
       it includes the lowest value).

    3. `.contour` and `.contourf` use a `marching squares
       <https://en.wikipedia.org/wiki/Marching_squares>`_ algorithm to
       compute contour locations.  More information can be found in
       `ContourPy documentation <https://contourpy.readthedocs.io>`_.
    """
    def __init__(self, z, x=None, y=None,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.contour.QuadContourSet
        self.mpl_plot_type = plt.contourf
        super().__init__(easing=easing,axis=axis,*args,**kwargs)
        self.x = np.ravel(z)
        self.y = np.ravel(z)
        self._x = x
        self._y = y
        if self._x is None:
            self._x = range(z.shape[0])
        if self._y is None:
            self._y = range(z.shape[1])
        self._x = np.array(self._x)
        self._y = np.array(self._y)
        self.init_shape = z.shape

    def morph(self,new_z,duration,delay=0,easing=None,persistent=True,**kwargs):
        self.anims.append({
            'name':'morph',
            'duration':duration,
            'delay':delay,
            'easing':easing,
            'new_x':np.ravel(new_z),
            'new_y':np.ravel(new_z),
            'persistent':persistent,
            'played':False
        })
        self.compute_timings()
        return self

    def function(self,data_x,data_y,x,kwargs):
        if isinstance(kwargs['alpha'],np.ndarray):
            kwargs['alpha'] = kwargs['alpha'][0]
        
        if 'bins' in kwargs:
            kwargs['bins'] = to_np_array(kwargs['bins'])

        if 'bins' in kwargs and len(kwargs['bins']) == 1:
            kwargs['bins'] = int(kwargs['bins'][0])
        
        if 'color' in kwargs:
            kwargs.pop('color')

        kwargs.pop('animated')

        if len(np.array(data_x).shape) == 1:
            new_data_x = np.zeros(self.init_shape)
            for i in range(0, len(data_x)):
                new_data_x[i//self.init_shape[0],i%self.init_shape[0]] = data_x[i]
            data_x = new_data_x
        
        #Have to reset xlim and ylim because contourf does not respect the imposed limits
        old_xlim = self.axis.get_xlim()
        old_ylim = self.axis.get_ylim()
        z = data_x
        self.obj = self.axis.contourf(self._x,self._y,z,**kwargs)
        self.axis.set_xlim(old_xlim)
        self.axis.set_ylim(old_ylim)

class text(plotObject):
    """
    Add text to the Axes.

    Add the text *s* to the Axes at location *x*, *y* in data coordinates,
    with a default ``horizontalalignment`` on the ``left`` and
    ``verticalalignment`` at the ``baseline``. 

    Parameters
    ----------
    x, y : float
        The position to place the text. By default, this is in data
        coordinates. The coordinate system can be changed using the
        *transform* parameter.

    duration : float
        Duration of the animation
    delay : float, default=0
        Delay before starting
    easing : callable, optional
        Easing function
    axis : matplotlib.axes.Axes, optional
        Axis to plot on


    s : str
        The text.

    fontdict : dict, default: None

        .. admonition:: Discouraged

           The use of *fontdict* is discouraged. Parameters should be passed as
           individual keyword arguments or using dictionary-unpacking
           ``text(..., **fontdict)``.

        A dictionary to override the default text properties. If fontdict
        is None, the defaults are determined by `.rcParams`.

    Returns
    -------
    `.Text`
        The created `.Text` instance.

    Other Parameters
    ----------------
    **kwargs : `~matplotlib.text.Text` properties.
        Other miscellaneous text parameters.

        Properties:
        agg_filter: a filter function, which takes a (m, n, 3) float array and a dpi value, and returns a (m, n, 3) array and two offsets from the bottom left corner of the image
        alpha: float or None
        animated: bool
        antialiased: bool
        backgroundcolor: color
        bbox: dict with properties for `.patches.FancyBboxPatch`
        clip_box: unknown
        clip_on: unknown
        clip_path: unknown
        color or c: color
        figure: `~matplotlib.figure.Figure` or `~matplotlib.figure.SubFigure`
        fontfamily or family or fontname: {FONTNAME, 'serif', 'sans-serif', 'cursive', 'fantasy', 'monospace'}
        fontproperties or font or font_properties: `.font_manager.FontProperties` or `str` or `pathlib.Path`
        fontsize or size: float or {'xx-small', 'x-small', 'small', 'medium', 'large', 'x-large', 'xx-large'}
        fontstretch or stretch: {a numeric value in range 0-1000, 'ultra-condensed', 'extra-condensed', 'condensed', 'semi-condensed', 'normal', 'semi-expanded', 'expanded', 'extra-expanded', 'ultra-expanded'}
        fontstyle or style: {'normal', 'italic', 'oblique'}
        fontvariant or variant: {'normal', 'small-caps'}
        fontweight or weight: {a numeric value in range 0-1000, 'ultralight', 'light', 'normal', 'regular', 'book', 'medium', 'roman', 'semibold', 'demibold', 'demi', 'bold', 'heavy', 'extra bold', 'black'}
        gid: str
        horizontalalignment or ha: {'left', 'center', 'right'}
        in_layout: bool
        label: object
        linespacing: float (multiple of font size)
        math_fontfamily: str
        mouseover: bool
        multialignment or ma: {'left', 'right', 'center'}
        parse_math: bool
        path_effects: list of `.AbstractPathEffect`
        picker: None or bool or float or callable
        position: (float, float)
        rasterized: bool
        rotation: float or {'vertical', 'horizontal'}
        rotation_mode: {None, 'default', 'anchor'}
        sketch_params: (scale: float, length: float, randomness: float)
        snap: bool or None
        text: object
        transform: `~matplotlib.transforms.Transform`
        transform_rotates_text: bool
        url: str
        usetex: bool, default: text.usetex
        verticalalignment or va: {'baseline', 'bottom', 'center', 'center_baseline', 'top'}
        visible: bool
        wrap: bool
        x: float
        y: float
        zorder: float

    Notes
    -----

    .. note::

        This is the :ref:`pyplot wrapper <pyplot_interface>` for `.axes.Axes.text`.

    Examples
    --------
    Individual keyword arguments can be used to override any given
    parameter::

        >>> text(x, y, s, fontsize=12)

    The default transform specifies that text is in data coords,
    alternatively, you can specify text in axis coords ((0, 0) is
    lower-left and (1, 1) is upper-right).  The example below places
    text in the center of the Axes::

        >>> text(0.5, 0.5, 'matplotlib', horizontalalignment='center',
        ...      verticalalignment='center', transform=ax.transAxes)

    You can put a rectangular box around the text instance (e.g., to
    set a background color) by using the keyword *bbox*.  *bbox* is
    a dictionary of `~matplotlib.patches.Rectangle`
    properties.  For example::

        >>> text(x, y, s, bbox=dict(facecolor='red', alpha=0.5))
    """
    def __init__(self,x,y,string,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.patches.PathPatch
        self.mpl_plot_type = plt.text
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.x = x
        self.y = y
        self.string = string

    def anim_function(self,x,kwargs):
        s = self.string
        for anim in self.anims:
            if anim['name'] not in ['draw','sequence']:
                continue
            t = self.get_t_from_x(anim,x)
            if anim['name'] == 'sequence':
                if x < anim['delay'] or x > anim['delay'] + anim['duration']:
                    continue
                _i = max(min(round(t*len(s)),len(s)-1),0)
                s = s[_i]
            elif anim['name'] == 'draw':
                if anim['reverse']:
                    i_max = max(round((1-t)*len(s)),0)
                else:
                    i_max = min(round(t*len(s)),len(s))
                s = s[:i_max]
        
        self.function(self.x,self.y,s,kwargs)

    def function(self,data_x,data_y,s,kwargs):
        if len(s) == 0:
            return
        if isinstance(kwargs['alpha'],np.ndarray):
            kwargs['alpha'] = kwargs['alpha'][0]
        
        if 'fontsize' in kwargs:
            fp = FontProperties(size=kwargs['fontsize'])
            kwargs.pop('fontsize')
        else:
            fp = FontProperties()
        tp = TextPath((0, 0), s, prop=fp)
        patch = PathPatch(tp, **kwargs)
        self.axis.add_patch(patch)

        px_per_pt = self.axis.get_figure().dpi / 72.0
        dx_per_px = (self.axis.get_xlim()[1] - self.axis.get_xlim()[0]) / self.axis.bbox.width
        dy_per_px = (self.axis.get_ylim()[1] - self.axis.get_ylim()[0]) / self.axis.bbox.height
        sx = px_per_pt * dx_per_px
        sy = px_per_pt * dy_per_px

        T = (
            transforms.Affine2D()
            .scale(sx, sy)
            .translate(data_x, data_y)
        )
        patch.set_path(patch.get_path().transformed(T))
        self.path = patch.get_path()
        self.obj = patch

class svg(plotObject):
    """A vector SVG object.

    Parameters
    ----------
    data : str
        SVG object as a string.
    fc : color, default=None
        the face color.
    ec : color, default='k'
        the edge color.
    lw : float, default=2
        the line width.
    """
    def __init__(self, data, fc=None, ec='k', lw=2,easing=None,axis=None, *args, **kwargs):
        self.mpl_obj_type = mpl.patches.PathPatch
        kwargs['facecolor'] = fc
        kwargs['edgecolor'] = ec
        kwargs['linewidth'] = lw
        super().__init__(easing=easing,axis=axis,*args, **kwargs)
        self.data = data
        self.path = None

    def draw_svg(self,kwargs):
        self.obj = mpl.patches.PathPatch(self.path,**kwargs)
        self.axis.add_patch(self.obj)

    def _slice_path(self, path, i0, i1):
        verts = path.vertices[i0:i1]
        if len(verts) == 0:
            return None
        codes = np.full(len(verts), mpl.path.Path.LINETO, dtype=np.uint8)
        codes[0] = mpl.path.Path.MOVETO
        return mpl.path.Path(verts, codes)

    def anim_function(self,x,kwargs):
        self.path = parse_path(self.data)
        path = self.path
        n = len(path.vertices)

        i0, i1 = 0, n
        has_path_anim = False

        for anim in self.anims:
            if anim['name'] not in ['draw','sequence']:
                continue
            if x < anim['delay'] or x > anim['delay'] + anim['duration']:
                continue
            
            has_path_anim = True
            t = self.get_t_from_x(anim,x)

            if anim['name'] == 'draw':
                if anim['reverse']:
                    i0, i1 = 0, max(round((1 - t) * n), 0)
                else:
                    i0, i1 = 0, min(round(t * n), n)
            elif anim['name'] == 'sequence':
                i = max(min(round(t * (n - 1)), n - 1), 0)
                i0, i1 = max(i - 1, 0), min(i + 1, n)
        
        frame_path = self._slice_path(path, i0, i1) if has_path_anim else path
        if frame_path is None:
            return
        self.path = frame_path
        self.function(self.x, self.y, None, kwargs)

    def function(self,data_x,data_y,x,kwargs):
        if isinstance(kwargs['alpha'],np.ndarray):
            kwargs['alpha'] = kwargs['alpha'][0]
        if kwargs['facecolor'] is None:
            kwargs['facecolor'] = self.axis._get_lines.get_next_color()
        
        if 'color' in kwargs:
            kwargs.pop('color')

        self.draw_svg(kwargs)
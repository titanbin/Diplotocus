import numpy as np
import sys, inspect
#----------------------------------------------
# EASING CLASSES
#----------------------------------------------
#TODO: add invert method to easing to behave in the inverted way so all inverted animations can work both ways
#TODO: change plot of easings.ipynb like this : https://api.flutter.dev/flutter/animation/Curves/easeInBack-constant.html

class Easing:
    def __init__(self, func=None):
        self.func = func if func is not None else (lambda x: x)
    
    def ease(self,x):
        return self.func(x)
    
class easeCubicBezier(Easing):
    def bezier(self, t, a1, a2):
        return (
            3 * (1 - t)**2 * t * a1
            + 3 * (1 - t) * t**2 * a2
            + t**3
        )

    def bezier_derivative(self, t, a1, a2):
        return (
            3 * (1 - t)**2 * a1
            + 6 * (1 - t) * t * (a2 - a1)
            + 3 * t**2 * (1 - a2)
        )

    def ease(self, times):
        times = np.asarray(times, dtype=float)
        times_clipped = np.clip(times, 0.0, 1.0)

        # Initial guess: t ≈ x
        t = times_clipped.copy()

        # Newton–Raphson (vectorized)
        for _ in range(self.max_iter):
            x_t = self.bezier(t, self.x1, self.x2)
            dx = x_t - times_clipped

            if np.all(np.abs(dx) < self.epsilon):
                break

            dxd_t = self.bezier_derivative(t, self.x1, self.x2)
            mask = np.abs(dxd_t) > 1e-8
            if isinstance(t,np.ndarray):
                t[mask] -= dx[mask] / dxd_t[mask]
            else:
                t -= dx[mask] / dxd_t[mask]

            # Keep t in bounds
            t = np.clip(t, 0.0, 1.0)

        # Compute y(t)
        y = self.bezier(t, self.y1, self.y2)

        # Respect exact endpoints
        if isinstance(y,np.ndarray):
            y[times <= 0.0] = 0.0
            y[times >= 1.0] = 1.0
        else:
            if times <= 0.0:
                y = 0.0
            elif times >= 1.0:
                y = 1.0

        if isinstance(y,np.ndarray) and len(y) == 1:
            return y[0]
        return y
        

    def __init__(self,x1,y1,x2,y2,epsilon=1e-6, max_iter=10):
        self.x1 = x1
        self.x2 = x2
        self.y1 = y1
        self.y2 = y2
        self.epsilon = epsilon
        self.max_iter = max_iter

#LINEAR
class easeLinear(Easing):
    def __init__(self):
        pass

    def func(self,x):
        return x

# SINE
class easeInSine(Easing):
    def __init__(self):
        super().__init__(lambda x:1 - np.cos((x * np.pi) / 2))

class easeOutSine(Easing):
    def __init__(self):
        super().__init__(lambda x: np.sin((x * np.pi) / 2))

class easeInOutSine(Easing):
    def __init__(self):
        super().__init__(lambda x: -(np.cos(np.pi * x) - 1) / 2)

# QUADRATIC
class easeInQuad(Easing):
    def __init__(self):
        super().__init__(lambda x: x**2)

class easeOutQuad(Easing):
    def __init__(self):
        super().__init__(lambda x: 1 - (1-x)**2)

class easeInOutQuad(Easing):
    def __init__(self):
        super().__init__(lambda x: np.where(x<0.5,2*x**2,1-(-2*x+2)**2 / 2))

# SUBIC
class easeInCubic(Easing):
    def __init__(self):
        super().__init__(lambda x: x**3)

class easeOutCubic(Easing):
    def __init__(self):
        super().__init__(lambda x: 1 - (1-x)**3)

class easeInOutCubic(Easing):
    def __init__(self):
        super().__init__(lambda x: np.where(x<0.5,4*x**3,1-(-2*x+2)**3 / 2))

# QUARTIC
class easeInQuart(Easing):
    def __init__(self):
        super().__init__(lambda x: x**4)

class easeOutQuart(Easing):
    def __init__(self):
        super().__init__(lambda x: 1-(1-x)**4)

class easeInOutQuart(Easing):
    def __init__(self):
        super().__init__(lambda x:np.where(x<0.5,8*x**4,1-(-2*x+2)**4 / 2))

# QUINTIC
class easeInQuint(Easing):
    def __init__(self):
        super().__init__(lambda x: x**5)

class easeOutQuint(Easing):
    def __init__(self):
        super().__init__(lambda x: 1-(1-x)**5)

class easeInOutQuint(Easing):
    def __init__(self):
        super().__init__(lambda x:np.where(x<0.5,16*x**5,1-(-2*x+2)**5 / 2))

# EXPONENTIAL
class easeInExpo(Easing):
    def __init__(self):
        super().__init__(lambda x:np.where(x==0,0,2**(10*x-10)))

class easeOutExpo(Easing):
    def __init__(self):
        super().__init__(lambda x:np.where(x==1,1,1-2**(-10*x)))

class easeInOutExpo(Easing):
    def __init__(self):
        super().__init__(lambda x:np.where(x==0,0,np.where(x==1,1,np.where(x<0.5,2**(20*x-10) / 2,(2-2**(-20*x+10)) / 2))))

# CIRCLE
class easeInCirc(Easing):
    def __init__(self):
        super().__init__(lambda x: 1 - np.sqrt(1 - x**2))

class easeOutCirc(Easing):
    def __init__(self):
        super().__init__(lambda x: np.sqrt(1 - (x - 1)**2))

class easeInOutCirc(Easing):
    def __init__(self):
        #(Math.sqrt(1 - Math.pow(-2 * x + 2, 2)) + 1) / 2
        #(np.sqrt(1 - (-2*x)**2) + 1) / 2
        super().__init__(lambda x:np.where(
            x<0.5,
            (1 - np.sqrt(np.abs(1 - (2*x)**2))) / 2,
            (np.sqrt(np.abs(1 - (-2*x+2)**2)) + 1) / 2)
        )

# BACK
class easeInBack(Easing):
    def __init__(self):
        def func(x):
            c1 = 1.70158
            c3 = c1 + 1

            return c3 * x * x * x - c1 * x * x
        super().__init__(func)

class easeOutBack(Easing):
    def __init__(self):
        def func(x):
            c1 = 1.70158
            c3 = c1 + 1

            return 1 + c3 * (x - 1)**3 + c1 * (x - 1)**2
        super().__init__(func)

class easeInOutBack(Easing):
    def __init__(self):
        def func(x):
            c1 = 1.70158
            c2 = c1 * 1.525

            return np.where(x < 0.5,
                ((2 * x)**2 * ((c2 + 1) * 2 * x - c2)) / 2,
                ((2 * x - 2)**2 * ((c2 + 1) * (x * 2 - 2) + c2) + 2) / 2
            )
        super().__init__(func)

# ELASTIC
class easeInElastic(Easing):
    def __init__(self):
        def func(x):
            c4 = (2 * np.pi) / 3

            return np.where(x == 0,0,np.where(x == 1,1,
                -2**(10 * x - 10) * np.sin((x * 10 - 10.75) * c4)
            ))
        super().__init__(func)

class easeOutElastic(Easing):
    def __init__(self):
        def func(x):
            c4 = (2 * np.pi) / 3

            return np.where(x == 0,0,np.where(x == 1,1,
                2**(-10 * x) * np.sin((x * 10 - 0.75) * c4) + 1
            ))
        super().__init__(func)

class easeInOutElastic(Easing):
    def __init__(self):
        def func(x):
            c5 = (2 * np.pi) / 4.5

            return np.where(x == 0,0,np.where(x == 1,1,np.where(x<0.5,
                -(2**(20 * x - 10) * np.sin((20 * x - 11.125) * c5)) / 2,
                (2**(-20 * x + 10) * np.sin((20 * x - 11.125) * c5)) / 2 + 1
            )))
        super().__init__(func)

# BOUNCE
def outBounce(x):
    n1 = 7.5625
    d1 = 2.75

    return np.where(x < 1 / d1,
        n1 * x * x,
    np.where(x < 2 / d1,
        n1 * (x - 1.5 / d1) * (x - 1.5 / d1) + 0.75,
    np.where(x < 2.5 / d1,
        n1 * (x - 2.25 / d1) * (x - 2.25 / d1) + 0.9375,
        n1 * (x - 2.625 / d1) * (x - 2.625 / d1) + 0.984375
    )))

class easeOutBounce(Easing):
    def __init__(self):
        super().__init__(outBounce)

class easeInBounce(Easing):
    def __init__(self):
        def func(x):
            x = 1-x
            return 1-outBounce(x)
        super().__init__(func)

class easeInOutBounce(Easing):
    def __init__(self):
        def func(x):
            return np.where(x<0.5,(1 - outBounce(1 - 2 * x)) / 2,(1 + outBounce(2 * x - 1)) / 2)
        super().__init__(func)

available_easings = []
for name, obj in inspect.getmembers(sys.modules[__name__]):
    if inspect.isclass(obj) and name != 'Easing':
        available_easings.append(name)
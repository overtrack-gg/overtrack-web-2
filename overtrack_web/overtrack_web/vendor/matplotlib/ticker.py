"""
Hacked port of parts of matplotlib/ticker.py to run standalone without needing numpy

"""

import sys

import itertools
import logging
import locale
import math
# import numpy as np
# from matplotlib import rcParams
# from matplotlib import cbook
# from matplotlib import transforms as mtransforms

import warnings

_log = logging.getLogger(__name__)


def isfinite(v):
    return v != float('+inf') and v != float('-inf') and v != float('nan')


def diff(a, n=1):
    assert n == 1
    return [a[i+1] - a[i] for i in range(len(a) - 1)]


def hstack(*ars):
    r = []
    for a in ars:
        if isinstance(a, list):
            r.extend(a)
        elif isinstance(a, (int, float)):
            r.append(a)
        else:
            raise ValueError()
    return r


class _Edge_integer:
    """
    Helper for MaxNLocator, MultipleLocator, etc.

    Take floating point precision limitations into account when calculating
    tick locations as integer multiples of a step.
    """

    def __init__(self, step, offset):
        """
        *step* is a positive floating-point interval between ticks.
        *offset* is the offset subtracted from the data limits
        prior to calculating tick locations.
        """
        if step <= 0:
            raise ValueError("'step' must be positive")
        self.step = step
        self._offset = abs(offset)

    def closeto(self, ms, edge):
        # Allow more slop when the offset is large compared to the step.
        if self._offset > 0:
            digits = math.log10(self._offset / self.step)
            tol = max(1e-10, 10 ** (digits - 12))
            tol = min(0.4999, tol)
        else:
            tol = 1e-10
        return abs(ms - edge) < tol

    def le(self, x):
        'Return the largest n: n*step <= x.'
        d, m = divmod(x, self.step)
        if self.closeto(m / self.step, 1):
            return (d + 1)
        return d

    def ge(self, x):
        'Return the smallest n: n*step >= x.'
        d, m = divmod(x, self.step)
        if self.closeto(m / self.step, 0):
            return d
        return (d + 1)


def scale_range(vmin, vmax, n=1, threshold=100):
    dv = abs(vmax - vmin)  # > 0 as nonsingular is called before.
    meanv = (vmax + vmin) / 2
    if abs(meanv) / dv < threshold:
        offset = 0
    else:
        offset = math.copysign(10 ** (math.log10(abs(meanv)) // 1), meanv)
    scale = 10 ** (math.log10(dv / n) // 1)
    return scale, offset


class Locator:
    """
    Determine the tick locations;

    Note, you should not use the same locator between different
    :class:`~matplotlib.axis.Axis` because the locator stores references to
    the Axis data and view limits
    """

    # Some automatic tick locators can generate so many ticks they
    # kill the machine when you try and render them.
    # This parameter is set to cause locators to raise an error if too
    # many ticks are generated.
    MAXTICKS = 1000

    def tick_values(self, vmin, vmax):
        """
        Return the values of the located ticks given **vmin** and **vmax**.

        .. note::
            To get tick locations with the vmin and vmax values defined
            automatically for the associated :attr:`axis` simply call
            the Locator instance::

                >>> print(type(loc))
                <type 'Locator'>
                >>> print(loc())
                [1, 2, 3, 4]

        """
        raise NotImplementedError('Derived must override')

    def set_params(self, **kwargs):
        """
        Do nothing, and rase a warning. Any locator class not supporting the
        set_params() function will call this.
        """
        warnings.warn("'set_params()' not defined for locator of type " +
                      str(type(self)))

    def __call__(self):
        """Return the locations of the ticks"""
        # note: some locators return data limits, other return view limits,
        # hence there is no *one* interface to call self.tick_values.
        raise NotImplementedError('Derived must override')

    def raise_if_exceeds(self, locs):
        """raise a RuntimeError if Locator attempts to create more than
           MAXTICKS locs"""
        if len(locs) >= self.MAXTICKS:
            raise RuntimeError("Locator attempting to generate {} ticks from "
                               "{} to {}: exceeds Locator.MAXTICKS".format(
                len(locs), locs[0], locs[-1]))
        return locs

    def view_limits(self, vmin, vmax):
        """
        select a scale for the range from vmin to vmax

        Normally this method is overridden by subclasses to
        change locator behaviour.
        """
        return vmin, vmax
        # return nonsingular(vmin, vmax)


class MaxNLocator(Locator):
    """
    Select no more than N intervals at nice locations.
    """
    default_params = dict(nbins=10,
                          steps=None,
                          integer=False,
                          symmetric=False,
                          prune=None,
                          min_n_ticks=2)

    def __init__(self, *args, **kwargs):
        """
        Keyword args:

        *nbins*
            Maximum number of intervals; one less than max number of
            ticks.  If the string `'auto'`, the number of bins will be
            automatically determined based on the length of the axis.

        *steps*
            Sequence of nice numbers starting with 1 and ending with 10;
            e.g., [1, 2, 4, 5, 10], where the values are acceptable
            tick multiples.  i.e. for the example, 20, 40, 60 would be
            an acceptable set of ticks, as would 0.4, 0.6, 0.8, because
            they are multiples of 2.  However, 30, 60, 90 would not
            be allowed because 3 does not appear in the list of steps.

        *integer*
            If True, ticks will take only integer values, provided
            at least `min_n_ticks` integers are found within the
            view limits.

        *symmetric*
            If True, autoscaling will result in a range symmetric
            about zero.

        *prune*
            ['lower' | 'upper' | 'both' | None]
            Remove edge ticks -- useful for stacked or ganged plots where
            the upper tick of one axes overlaps with the lower tick of the
            axes above it, primarily when :rc:`axes.autolimit_mode` is
            ``'round_numbers'``.  If ``prune=='lower'``, the smallest tick will
            be removed.  If ``prune == 'upper'``, the largest tick will be
            removed.  If ``prune == 'both'``, the largest and smallest ticks
            will be removed.  If ``prune == None``, no ticks will be removed.

        *min_n_ticks*
            Relax `nbins` and `integer` constraints if necessary to
            obtain this minimum number of ticks.

        """
        if args:
            kwargs['nbins'] = args[0]
            if len(args) > 1:
                raise ValueError(
                    "Keywords are required for all arguments except 'nbins'")
        self.set_params(**self.default_params)
        self.set_params(**kwargs)

    @staticmethod
    def _validate_steps(steps):
        if any(e <= 0 for e in diff(steps)):
            raise ValueError('steps argument must be uniformly increasing')
        if steps[-1] > 10 or steps[0] < 1:
            warnings.warn('Steps argument should be a sequence of numbers\n'
                          'increasing from 1 to 10, inclusive. Behavior with\n'
                          'values outside this range is undefined, and will\n'
                          'raise a ValueError in future versions of mpl.')
        if steps[0] != 1:
            steps = hstack((1, steps))
        if steps[-1] != 10:
            steps = hstack((steps, 10))
        return steps

    @staticmethod
    def _staircase(steps):
        # Make an extended staircase within which the needed
        # step will be found.  This is probably much larger
        # than necessary.
        # flights = (0.1 * steps[:-1], steps, 10 * steps[1])
        # return hstack(flights)
        return [0.1 * v for v in steps[:-1]] + list(steps) + [10 * steps[1]]

    def set_params(self, **kwargs):
        """Set parameters within this locator."""
        if 'nbins' in kwargs:
            self._nbins = kwargs['nbins']
            if self._nbins != 'auto':
                self._nbins = int(self._nbins)
        if 'symmetric' in kwargs:
            self._symmetric = kwargs['symmetric']
        if 'prune' in kwargs:
            prune = kwargs['prune']
            if prune is not None and prune not in ['upper', 'lower', 'both']:
                raise ValueError(
                    "prune must be 'upper', 'lower', 'both', or None")
            self._prune = prune
        if 'min_n_ticks' in kwargs:
            self._min_n_ticks = max(1, kwargs['min_n_ticks'])
        if 'steps' in kwargs:
            steps = kwargs['steps']
            if steps is None:
                self._steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
            else:
                self._steps = self._validate_steps(steps)
            self._extended_steps = self._staircase(self._steps)
        if 'integer' in kwargs:
            self._integer = kwargs['integer']

    def _raw_ticks(self, vmin, vmax):
        """
        Generate a list of tick locations including the range *vmin* to
        *vmax*.  In some applications, one or both of the end locations
        will not be needed, in which case they are trimmed off
        elsewhere.
        """
        if self._nbins == 'auto':
            nbins = 9
        else:
            nbins = self._nbins

        scale, offset = scale_range(vmin, vmax, nbins)
        _vmin = vmin - offset
        _vmax = vmax - offset
        raw_step = (_vmax - _vmin) / nbins
        steps = [e * scale for e in self._extended_steps]
        if self._integer:
            # For steps > 1, keep only integer values.
            # igood = (steps < 1) | (abs(steps - round(steps)) < 0.001)
            # steps = steps[igood]
            steps = [
                s
                for s in steps
                if (s < 1) or (abs(s) - round(s) < 0.001)
            ]

        # istep = np.nonzero(steps >= raw_step)[0][0]
        istep = [i for i, s in enumerate(steps) if s >= raw_step][0]

        # This is an upper limit; move to smaller steps if necessary.
        for istep in reversed(range(istep + 1)):
            step = steps[istep]

            if (self._integer and math.floor(_vmax) - math.ceil(_vmin) >= self._min_n_ticks - 1):
                step = max(1, step)
            best_vmin = (_vmin // step) * step

            # Find tick locations spanning the vmin-vmax range, taking into
            # account degradation of precision when there is a large offset.
            # The edge ticks beyond vmin and/or vmax are needed for the
            # "round_numbers" autolimit mode.
            edge = _Edge_integer(step, offset)
            low = edge.le(_vmin - best_vmin)
            high = edge.ge(_vmax - best_vmin)
            ticks = [v * step + best_vmin for v in range(int(low), int(high + 1))]
            # Count only the ticks that will be displayed.
            # nticks = ((ticks <= _vmax) & (ticks >= _vmin)).sum()
            nticks = sum((t <= _vmax) and (t >= _vmin) for t in ticks)
            if nticks >= self._min_n_ticks:
                break
        return [t + offset for t in ticks]

    # def __call__(self):
    #     vmin, vmax = self.axis.get_view_interval()
    #     return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        if self._symmetric:
            vmax = max(abs(vmin), abs(vmax))
            vmin = -vmax
        # vmin, vmax = nonsingular(
        #     vmin, vmax, expander=1e-13, tiny=1e-14)
        locs = self._raw_ticks(vmin, vmax)

        prune = self._prune
        if prune == 'lower':
            locs = locs[1:]
        elif prune == 'upper':
            locs = locs[:-1]
        elif prune == 'both':
            locs = locs[1:-1]
        return self.raise_if_exceeds(locs)

    def view_limits(self, dmin, dmax):
        if self._symmetric:
            dmax = max(abs(dmin), abs(dmax))
            dmin = -dmax

        # dmin, dmax = nonsingular(
        #     dmin, dmax, expander=1e-12, tiny=1e-13)

        return dmin, dmax


def main() -> None:
    import random
    mval = 545
    print(
        MaxNLocator(nbins=10, steps=(1, 3, 6, 10), prune='upper').tick_values(0, mval)
    )
    from matplotlib.ticker import MaxNLocator as MaxNLocator2
    print(
        MaxNLocator2(nbins=10, steps=(1, 3, 6, 10), prune='upper').tick_values(0, mval)
    )


if __name__ == '__main__':
    main()

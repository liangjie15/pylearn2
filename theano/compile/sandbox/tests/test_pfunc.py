import numpy
import unittest
import copy
import theano
from theano.tensor import Tensor, dmatrix, dvector, lscalar
from theano import tensor

from sharedvalue import *
from pfunc import *

class Test_pfunc(unittest.TestCase):

    def test_doc(self):
        """Ensure the code given in pfunc.txt works as expected"""

        # Example #1.
        a = lscalar()
        b = shared(1)
        f1 = pfunc([a], a+b)
        f2 = pfunc([Param(a, default=44)], a + b, updates={b: b + 1})
        self.failUnless(b.value == 1)
        self.failUnless(f1(3) == 4)
        self.failUnless(f2(3) == 4)
        self.failUnless(b.value == 2)
        self.failUnless(f1(3) == 5)
        b.value = 0
        self.failUnless(f1(3) == 3)

        # Example #2.
        a = tensor.lscalar()
        b = shared(7)
        f1 = pfunc([a], a + b)
        f2 = pfunc([a], a * b)
        self.failUnless(f1(5) == 12)
        b.value = 8
        self.failUnless(f1(5) == 13)
        self.failUnless(f2(4) == 32)

    def test_shared(self):

        # CHECK: two functions (f1 and f2) can share w
        w = shared(numpy.random.rand(2,2), 'w')
        wval = copy.copy(w.value)

        x = dmatrix()
        out1 = w + x
        out2 = w * x
        f1 = pfunc([x],[out1])
        f2 = pfunc([x],[out2])
        xval = numpy.random.rand(2,2)
        assert numpy.all(f1(xval) == xval + wval)
        assert numpy.all(f2(xval) == xval * wval)

        # CHECK: updating a shared value
        f3 = pfunc([x], out1, updates=[(w, w-1)])
        assert numpy.all(f3(xval) == xval + wval) # f3 changes the value of w
        assert numpy.all(f1(xval) == xval + (wval-1)) # this same value is read by f1

        w.value *= 10
        assert numpy.all(f1(xval) == xval + w.value) # this same value is read by f1

    def test_no_shared_as_input(self):
        """Test that shared variables cannot be used as function inputs."""
        w_init = numpy.random.rand(2,2)
        w = shared(w_init.copy(), 'w')
        try:
            f = pfunc([w], theano.tensor.sum(w * w))
            assert False
        except TypeError, e:
            msg = 'Cannot use a shared variable (w) as explicit input'
            if str(e).find(msg) < 0:
                raise

    def test_default_container(self):
        # Ensure it is possible to (implicitly) use a shared variable in a
        # function, as a 'state' that can be updated at will.

        rng = numpy.random.RandomState(1827)
        w_init = rng.rand(5)
        w = shared(w_init.copy(), 'w')
        reg = theano.tensor.sum(w*w)
        f = pfunc([], reg)

        assert f() == numpy.sum(w_init * w_init)
        # Change the value of w and ensure the output changes accordingly.
        w.value += 1.0
        assert f() == numpy.sum((w_init+1)**2)

    def test_default_scalar_container(self):
        # Similar in spirit to test_default_container, but updating a scalar
        # variable. This is a sanity check for non mutable types.
        x = shared(0.0, 'x')
        f = pfunc([], x)
        assert f() == 0
        x.value += 1
        assert f() == 1

    def test_param_strict(self):

        a = tensor.dvector()
        b = shared(7)
        out = a + b

        f = pfunc([Param(a, strict=False)], [out])
        f(numpy.random.rand(8)) # works, rand generates float64 by default
        f(numpy.array([1,2,3,4], dtype='int32')) # works, casting is allowed
        
        f = pfunc([Param(a, strict=True)], [out])
        try:
            f(numpy.array([1,2,3,4], dtype='int32')) # fails, f expects float64
        except TypeError:
            pass

    def test_param_mutable(self):
        a = tensor.dvector()
        b = shared(7)
        out = a + b

        a_out = a * 2 # assuming the op which makes this "in place" triggers

        # using mutable=True will let fip change the value in aval
        fip = pfunc([Param(a, mutable=True)], [a_out], mode='FAST_RUN')
        aval = numpy.random.rand(10)
        aval2 = aval.copy()
        assert numpy.all( fip(aval) == aval2*2 )
        assert not numpy.all( aval == aval2 )

        # using mutable=False should leave the input untouched
        f = pfunc([Param(a, mutable=False)], [a_out], mode='FAST_RUN')
        aval = numpy.random.rand(10)
        aval2 = aval.copy()
        assert numpy.all( f(aval) == aval2*2 )
        assert numpy.all( aval == aval2 )

    def test_shared_mutable(self):
        bval = numpy.arange(5)
        b = shared(bval)
        assert b.value is bval
        b_out = b * 2

        # by default, shared are not mutable unless doing an explicit update
        f = pfunc([], [b_out], mode='FAST_RUN')
        assert (f() ==  numpy.arange(5) * 2).all()
        assert all( b.value == numpy.arange(5))

        # using updates, b is now a mutable parameter
        f = pfunc([], [b_out], updates=[(b, b_out)], mode='FAST_RUN')
        assert (f() == numpy.arange(5)*2 ).all()
        assert all( b.value == numpy.arange(5)*2) # because of the update
        assert all( bval == numpy.arange(5)*2) # because of mutable=True

        # do not depend on updates being in-place though!
        bval = numpy.arange(5)
        b.value = bval
        f = pfunc([], [b_out], updates=[(b, b_out+3)], mode='FAST_RUN')
        assert ( f() == numpy.arange(5)*2 ).all()
        assert (b.value == ((numpy.arange(5)*2)+3)).all() # because of the update
        # bval got modified to something...
        assert not all(bval == numpy.arange(5))
        # ... but not to b.value !
        assert not (bval == b.value).all()

    def test_update(self):
        """Test update mechanism in different settings."""

        # Simple value assignment.
        x = shared(0)
        assign = pfunc([], [], updates = {x: 3})
        assign()
        self.failUnless(x.value == 3)

        # Same but using a mutable constant to show how it can be used to
        # modify the update value after the function is created.
        x.value = 0
        y = numpy.ones(())
        assign_mutable = pfunc([], [], updates = {x: y})
        assign_mutable()
        self.failUnless(x.value == 1)
        y.fill(4)
        assign_mutable()
        self.failUnless(x.value == 4)

        # Basic increment function.
        x.value = 0
        inc = pfunc([], [], updates = {x: x + 1})
        inc()
        self.failUnless(x.value == 1)

        # Increment by a constant value.
        x.value = -1
        y = shared(2)
        inc_by_y = pfunc([], [], updates = {x: x + y})
        inc_by_y()
        self.failUnless(x.value == 1)


if __name__ == '__main__':
    theano.compile.mode.default_mode = 'FAST_COMPILE'
    Test_pfunc().test_default_scalar_container()


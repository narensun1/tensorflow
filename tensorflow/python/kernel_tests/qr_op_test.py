# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for tensorflow.ops.math_ops.matrix_inverse."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np

from tensorflow.python.framework import constant_op
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import linalg_ops
from tensorflow.python.ops import math_ops
from tensorflow.python.platform import test


def _AddTest(test_class, op_name, testcase_name, fn):
  test_name = "_".join(["test", op_name, testcase_name])
  if hasattr(test_class, test_name):
    raise RuntimeError("Test %s defined more than once" % test_name)
  setattr(test_class, test_name, fn)


class QrOpTest(test.TestCase):

  def testWrongDimensions(self):
    # The input to qr should be a tensor of at least rank 2.
    scalar = constant_op.constant(1.)
    with self.assertRaisesRegexp(ValueError,
                                 "Shape must be at least rank 2 but is rank 0"):
      linalg_ops.qr(scalar)
    vector = constant_op.constant([1., 2.])
    with self.assertRaisesRegexp(ValueError,
                                 "Shape must be at least rank 2 but is rank 1"):
      linalg_ops.qr(vector)


def _GetQrOpTest(dtype_, shape_, full_matrices_, use_static_shape_):

  is_complex = dtype_ in (np.complex64, np.complex128)
  is_single = dtype_ in (np.float32, np.complex64)

  def CompareOrthogonal(self, x, y, rank):
    if is_single:
      atol = 5e-4
    else:
      atol = 5e-14
    # We only compare the first 'rank' orthogonal vectors since the
    # remainder form an arbitrary orthonormal basis for the
    # (row- or column-) null space, whose exact value depends on
    # implementation details. Notice that since we check that the
    # matrices of singular vectors are unitary elsewhere, we do
    # implicitly test that the trailing vectors of x and y span the
    # same space.
    x = x[..., 0:rank]
    y = y[..., 0:rank]
    # Q is only unique up to sign (complex phase factor for complex matrices),
    # so we normalize the sign first.
    sum_of_ratios = np.sum(np.divide(y, x), -2, keepdims=True)
    phases = np.divide(sum_of_ratios, np.abs(sum_of_ratios))
    x *= phases
    self.assertAllClose(x, y, atol=atol)

  def CheckApproximation(self, a, q, r):
    if is_single:
      tol = 1e-5
    else:
      tol = 1e-14
    # Tests that a ~= q*r.
    a_recon = math_ops.matmul(q, r)
    self.assertAllClose(a_recon.eval(), a, rtol=tol, atol=tol)

  def CheckUnitary(self, x):
    # Tests that x[...,:,:]^H * x[...,:,:] is close to the identity.
    xx = math_ops.matmul(math_ops.conj(x), x, transpose_a=True)
    identity = array_ops.matrix_band_part(array_ops.ones_like(xx), 0, 0)
    if is_single:
      tol = 1e-5
    else:
      tol = 1e-14
    self.assertAllClose(identity.eval(), xx.eval(), atol=tol)

  def Test(self):
    np.random.seed(1)
    x_np = np.random.uniform(
        low=-1.0, high=1.0, size=np.prod(shape_)).reshape(shape_).astype(dtype_)
    if is_complex:
      x_np += 1j * np.random.uniform(
          low=-1.0, high=1.0,
          size=np.prod(shape_)).reshape(shape_).astype(dtype_)

    # TODO(rmlarsen): Debug failure due to invalid parameter to ORMQR.
    rows_ = shape_[-2]
    cols_ = shape_[-1]
    use_gpu = False if rows_ < cols_ or (full_matrices_ and
                                         rows_ != cols_) else True

    with self.test_session(use_gpu=use_gpu) as sess:
      if use_static_shape_:
        x_tf = constant_op.constant(x_np)
      else:
        x_tf = array_ops.placeholder(dtype_)
      q_tf, r_tf = linalg_ops.qr(x_tf, full_matrices=full_matrices_)

      if use_static_shape_:
        q_tf_val, r_tf_val = sess.run([q_tf, r_tf])
      else:
        q_tf_val, r_tf_val = sess.run([q_tf, r_tf], feed_dict={x_tf: x_np})

      q_dims = q_tf_val.shape
      np_q = np.ndarray(q_dims, dtype_)
      np_q_reshape = np.reshape(np_q, (-1, q_dims[-2], q_dims[-1]))
      new_first_dim = np_q_reshape.shape[0]

      x_reshape = np.reshape(x_np, (-1, x_np.shape[-2], x_np.shape[-1]))
      for i in range(new_first_dim):
        if full_matrices_:
          np_q_reshape[i,:,:], _ = \
                np.linalg.qr(x_reshape[i,:,:], mode="complete")
        else:
          np_q_reshape[i,:,:], _ = \
                np.linalg.qr(x_reshape[i,:,:], mode="reduced")
      np_q = np.reshape(np_q_reshape, q_dims)
      CompareOrthogonal(self, np_q, q_tf_val, min(shape_[-2:]))
      CheckApproximation(self, x_np, q_tf_val, r_tf_val)
      CheckUnitary(self, q_tf_val)

  return Test


if __name__ == "__main__":
  for dtype in np.float32, np.float64, np.complex64, np.complex128:
    for rows in 1, 2, 5, 10, 32, 100:
      for cols in 1, 2, 5, 10, 32, 100:
        for full_matrices in False, True:
          for batch_dims in [(), (3,)] + [(3, 2)] * (max(rows, cols) < 10):
            for use_static_shape in True, False:
              shape = batch_dims + (rows, cols)
              name = "%s_%s_full_%s_static_%s" % (dtype.__name__,
                                                  "_".join(map(str, shape)),
                                                  full_matrices,
                                                  use_static_shape)
              _AddTest(QrOpTest, "Qr", name,
                       _GetQrOpTest(dtype, shape, full_matrices,
                                    use_static_shape))
  test.main()

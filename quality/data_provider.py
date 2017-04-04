"""This data provider reads TFRecords of image and label data.

The TFRecords contain TF Example protos with full-size images and labels. Either
a random cropped patch of the image, or all of the tiles within an image are
extracted and converted to batched tensors, ready for training or inference.
"""

# Copyright 2017 Google Inc.
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

import os

import numpy as np

from tensorflow.contrib.slim import dataset
from tensorflow.contrib.slim import dataset_data_provider
from tensorflow.contrib.slim import tfexample_decoder
import tensorflow as tf

import logging

IMAGE_WIDTH = 520
IMAGE_HEIGHT = 520
FEATURE_IMAGE = 'image'
FEATURE_IMAGE_CLASS = 'image/class'
FEATURE_IMAGE_PATH = 'image/path'
_ITEMS_TO_DESCRIPTIONS = {
    FEATURE_IMAGE: 'A [width x width x 1] grayscale image.',
    FEATURE_IMAGE_CLASS: 'A single integer between 0 and [num_classes-1]',
    FEATURE_IMAGE_PATH: 'A string indicating path to image.',
}
# Range of random brightness factors to scale training data.
_BRIGHTNESS_MIN_FACTOR = 0.2
_BRIGHTNESS_MAX_FACTOR = 5.0
# Range of random image brightness offsets for training data.
_BRIGHTNESS_MIN_OFFSET = 1.0 / 65535
_BRIGHTNESS_MAX_OFFSET = 1000.0 / 65535


def get_filename_num_records(tf_record_path):
  """Get path to text file containing number of records.

  Args:
    tf_record_path: String, path to TFRecord file.

  Returns:
    String, path to text file containing number of records in TFRecord file.
  """
  return os.path.splitext(tf_record_path)[0] + '.num_records'


def get_num_records(tf_record_path):
  """Get the number of records in a TFRecord by reading it from the text file.

  Args:
    tf_record_path: String, path to TFRecord file.

  Returns:
    Integer, number of records in TFRecord file, as read form the text file.
  """
  num_records_path = get_filename_num_records(tf_record_path)
  with open(num_records_path, 'r') as f:
    num_records = int(f.read())
    logging.info('%d records in %s.', num_records, num_records_path)
    return num_records


def get_split(split_name, tfrecord_file_pattern, num_classes, image_width,
              image_height):
  """Gets a dataset tuple from tfrecord, to be used with DatasetDataProvider.

  Args:
    split_name: String, a train/test split name.
    tfrecord_file_pattern: String, with formatting for split name. E.g.
      'file_%s.tfrecord'.
    num_classes: Integer representing number of classes. Must match data in
      the TFRecord.
    image_width: Integer, width of image size to be cropped.
    image_height: Integer, height of image size to be cropped.

  Returns:
    A `Dataset` namedtuple.

  Raises:
    ValueError: if `split_name` is not a valid train/test split.
  """
  # Input images, each which will be modified in one of 'num_classes' ways.
  valid_splits = {'train', 'test'}
  if split_name not in valid_splits:
    raise ValueError('split name %s was not recognized.' % split_name)

  if image_height <= 0 or image_width <= 0:
    raise ValueError('Invalid image_height and/or image_width: %d, %d.' %
                     image_height, image_width)
  image_shape = (image_height, image_width, 1)
  keys_to_features = {
      FEATURE_IMAGE:
          tf.FixedLenFeature(
              image_shape, tf.float32, default_value=tf.zeros(image_shape)),
      FEATURE_IMAGE_CLASS:
          tf.FixedLenFeature(
              [num_classes], tf.float32, default_value=tf.zeros([num_classes])),
      FEATURE_IMAGE_PATH:
          tf.FixedLenFeature(
              [1], tf.string, default_value=''),
  }

  items_to_handlers = {
      FEATURE_IMAGE: tfexample_decoder.Tensor(FEATURE_IMAGE),
      FEATURE_IMAGE_CLASS: tfexample_decoder.Tensor(FEATURE_IMAGE_CLASS),
      FEATURE_IMAGE_PATH: tfexample_decoder.Tensor(FEATURE_IMAGE_PATH),
  }

  decoder = tfexample_decoder.TFExampleDecoder(keys_to_features,
                                               items_to_handlers)

  file_pattern = tfrecord_file_pattern % split_name

  num_samples = get_num_records(file_pattern)
  return dataset.Dataset(
      data_sources=file_pattern,
      reader=tf.TFRecordReader,
      decoder=decoder,
      num_samples=num_samples,
      num_classes=num_classes,
      items_to_descriptions=_ITEMS_TO_DESCRIPTIONS)


def get_batches(image, label, image_path, num_threads=800, batch_size=32):
  """Converts image and label into batches.

  Args:
    image: Input image tensor, size [num_images x width x width x 1].
    label: Input label tensor, size [num_images x num_classes].
    image_path: Input image path tensor, size [num_images x 1].
    num_threads: Integer, number of threads for preprocessing and loading data.
    batch_size: Integer, batch size for the output.

  Returns:
    Batched version of the inputs: images (shape [batch_size x width x width x
    1]), labels (shape [batch_size x num_classes]) and image_paths (shape
    [batch_size x 1]) tensors.
  """
  assert len(image.get_shape().as_list()) == 4
  batch_images, batch_one_hot_labels, batch_image_paths = tf.train.batch(
      [image, label, image_path],
      batch_size=batch_size,
      num_threads=num_threads,
      capacity=5 * batch_size,
      enqueue_many=True)
  return batch_images, batch_one_hot_labels, batch_image_paths


def get_image_patch_tensor(image, label, image_path, patch_width):
  """Crops a random patch from image.

  Args:
    image: Input image tensor, size [width x width x 1].
    label: Input label tensor, size [num_classes].
    image_path: Input image path tensor, size [1].
    patch_width: Integer representing width of image patch.
  Returns:
    Tensors image patch, size [1 x patch_width x patch_width x 1],
    expanded_label, size [1 x num_classes], and expanded_image_path, size
    [1 x 1].
  """
  assert len(image.get_shape().as_list()) == 3, image.get_shape().as_list()
  size = tf.constant([patch_width, patch_width, 1], dtype=tf.int32)

  patch = tf.expand_dims(tf.random_crop(image, size), 0)

  expanded_label = tf.expand_dims(label, dim=0)
  expanded_image_path = tf.expand_dims(image_path, dim=0)
  return patch, expanded_label, expanded_image_path


def apply_random_offset(patch, min_offset, max_offset):
  """Adds a random offset to input image (tensor)."""
  # Choose offset uniformly in log space.
  offset = tf.pow(
      tf.constant([10.0]),
      tf.random_uniform([1], np.log10(min_offset), np.log10(max_offset)))
  return tf.add(patch, offset)


def apply_random_brightness_adjust(patch, min_factor, max_factor):
  """Scales the input image (tensor) brightness by a random factor."""
  # Choose brightness scale uniformly in log space.
  brightness = tf.pow(
      tf.constant([10.0]),
      tf.random_uniform([1], np.log10(min_factor), np.log10(max_factor)))
  return tf.multiply(patch, brightness)


def get_image_tiles_tensor(image, label, image_path, patch_width):
  """Gets patches that tile the input image, starting at upper left.

  Args:
    image: Input image tensor, size [height x width x 1].
    label: Input label tensor, size [num_classes].
    image_path: Input image path tensor, size [1].
    patch_width: Integer representing width of image patch.

  Returns:
    Tensors tiles, size [num_tiles x patch_width x patch_width x 1], labels,
    size [num_tiles x num_classes], and image_paths, size [num_tiles x 1].
  """
  assert len(image.get_shape().as_list()) == 3
  size = tf.constant([patch_width, patch_width], dtype=tf.int32)
  image_height, image_width, _ = image.get_shape().as_list()
  expanded_label = tf.expand_dims(label, dim=0)
  expanded_image_path = tf.expand_dims(image_path, dim=0)
  for j in range(image_height / patch_width):
    for i in range(image_width / patch_width):
      offsets = tf.constant(
          np.array(
              [[(j + 0.5) * patch_width, (i + 0.5) * patch_width]],
              dtype=np.float32))
      patch = tf.image.extract_glimpse(
          tf.expand_dims(
              image, dim=0),
          size,
          offsets,
          centered=False,
          normalized=False)
      if i == 0 and j == 0:
        tiles = patch
        labels = expanded_label
        image_paths = expanded_image_path
      else:
        tiles = tf.concat([tiles, patch], 0)
        labels = tf.concat([labels, expanded_label], 0)
        image_paths = tf.concat([image_paths, expanded_image_path], 0)

  return tiles, labels, image_paths


def provide_data(tfrecord_file_pattern,
                 split_name,
                 batch_size,
                 num_classes,
                 image_width,
                 image_height,
                 patch_width=28,
                 randomize=True,
                 num_threads=64):
  """Provides batches of data.

  Args:
    tfrecord_file_pattern: String, with formatting for split name. E.g.
      'file_%s.tfrecord'.
    split_name: String indicating split name, typically 'train' or 'test'.
    batch_size: The number of images in each batch. If 'randomize' is False,
      the batch size must be the number of tiles per image.
    num_classes: Integer representing number of classes.
    image_width: Integer, width of image size to be cropped.
    image_height: Integer, height of image size to be cropped.
    patch_width: Integer width (and height) of image patch.
    randomize: Boolean indicating whether to use image patches that are randomly
      cropped, with a random offset and brightness adjustment applied. Use only
      for training.
    num_threads: Number of threads for data reading queue. Use only 1 thread for
      deterministic ordering of inputs.


  Returns:
    batch_images: A `Tensor` of size [batch_size, patch_width, patch_width, 1]
    batch_one_hot_labels: A `Tensor` of size [batch_size, num_classes], where
      each row has a single element set to one and the rest set to zeros.
    num_samples: The number of images (not tiles) in the dataset.

  Raises:
    ValueError: If the batch size is invalid.
  """
  if batch_size <= 0:
    raise ValueError('Invalid batch size: %d' % batch_size)
  dataset_info = get_split(
      split_name,
      tfrecord_file_pattern,
      num_classes,
      image_width=image_width,
      image_height=image_height)
  provider = dataset_data_provider.DatasetDataProvider(
      dataset_info,
      common_queue_capacity=2 * batch_size,
      common_queue_min=batch_size,
      shuffle=False,
      num_readers=num_threads)

  # image, label, image_path have shape [width x width x 1], [num_classes], [1].
  [image, label, image_path] = provider.get(
      [FEATURE_IMAGE, FEATURE_IMAGE_CLASS, FEATURE_IMAGE_PATH])

  logging.info('Data provider image shape: %s', str(image.get_shape().as_list()))
  if randomize:
    # For training, get a single randomly cropped image patch.
    patch_original, label, image_path = get_image_patch_tensor(
        image, label, image_path, patch_width=patch_width)

    # Apply a random offset and brightness adjustment.
    patch_scaled = apply_random_brightness_adjust(
        patch_original,
        min_factor=_BRIGHTNESS_MIN_FACTOR,
        max_factor=_BRIGHTNESS_MAX_FACTOR)

    patch = apply_random_offset(
        patch_scaled,
        min_offset=_BRIGHTNESS_MIN_OFFSET,
        max_offset=_BRIGHTNESS_MAX_OFFSET)

    batch_images, batch_one_hot_labels, batch_image_paths = get_batches(
        patch,
        label,
        image_path,
        batch_size=batch_size,
        num_threads=num_threads)
  else:
    # For testing extract tiles that perfectly tile (without overlap) the image.
    tiles, labels, image_paths = get_image_tiles_tensor(
        image, label, image_path, patch_width=patch_width)

    num_tiles = tiles.get_shape().as_list()[0]
    assert num_tiles == batch_size, 'num_tiles: %d, batch_size: %d' % (
        num_tiles, batch_size)

    batch_images, batch_one_hot_labels, batch_image_paths = get_batches(
        tiles,
        labels,
        image_paths,
        batch_size=num_tiles,
        num_threads=num_threads)
  num_samples = provider.num_samples()
  return batch_images, batch_one_hot_labels, batch_image_paths, num_samples
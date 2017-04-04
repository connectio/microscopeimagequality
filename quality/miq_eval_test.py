"""Unittest for miq_eval.py."""
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
from PIL import Image

import tempfile
import  tensorflow.contrib.slim as slim
import tensorflow as tf

import unittest
from quality import miq_eval

FLAGS = tf.app.flags.FLAGS


class MiqEvalTest(tf.test.TestCase):

  def setUp(self):
    self.batch_size = 4
    self.test_data_directory = os.path.join(os.path.dirname(os.path.abspath(__file__))
,"testdata")
    self.test_dir = tempfile.mkdtemp()    
    self.patch_width = 28
    self.image_shape = (int(np.sqrt(self.batch_size) * self.patch_width),
                        int(np.sqrt(self.batch_size) * self.patch_width))

  def testAnnotatePatch(self):
    image_width = 28
    image = np.expand_dims(
        np.expand_dims(
            np.ones((image_width, image_width)), axis=0), axis=3)
    annotated_image = miq_eval.annotate_patch(image, prediction=0, label=0)
    expected_image_width = (
        image_width * miq_eval._IMAGE_ANNOTATION_MAGNIFICATION_PERCENT / 100)
    self.assertEquals(annotated_image.shape,
                      (1, expected_image_width, expected_image_width, 1))

    def check_image_matches_golden(prediction, label):
      annotated_image = miq_eval.annotate_patch(
          image, prediction=prediction, label=label)
      test_image = np.squeeze(annotated_image).astype(np.uint8)
      golden = np.array(
          Image.open(
              os.path.join(self.test_data_directory,
                           'annotated_image_predicted_{}_label_{}.png'.format(
                               prediction, label))))
      self.assertEquals(golden.shape, test_image.shape)
      self.assertEquals(golden.dtype, test_image.dtype)

      np.testing.assert_array_equal(golden, test_image)

    check_image_matches_golden(0, 0)
    check_image_matches_golden(0, 1)
    check_image_matches_golden(1, 0)
    check_image_matches_golden(1, 1)

  def testAnnotateClassificationErrorsRuns(self):
    num_classes = 5
    images = tf.zeros([self.batch_size, self.patch_width, self.patch_width, 1])
    predictions = tf.zeros([self.batch_size,])
    labels = tf.zeros([self.batch_size,])
    probabilities = tf.zeros([self.batch_size, num_classes])
    miq_eval.annotate_classification_errors(images, predictions, labels,
                                            probabilities, self.image_shape[0],
                                            self.image_shape[1])

  def testAnnotateClassificationErrorsRunsInTensorFlow(self):
    g = tf.Graph()
    with g.as_default():
      num_classes = 5
      images = tf.zeros(
          [self.batch_size, self.patch_width, self.patch_width, 1])
      predictions = tf.zeros([self.batch_size,])
      labels = tf.zeros([self.batch_size,])
      probabilities = tf.zeros([self.batch_size, num_classes])
      image, summary = miq_eval.annotate_classification_errors(
          images, predictions, labels, probabilities, self.image_shape[0],
          self.image_shape[1])

      sv = tf.train.Supervisor()
      with sv.managed_session() as sess:
        [_, image_np] = sess.run([summary, image])
      self.assertEqual((1, self.patch_width * np.sqrt(self.batch_size),
                        self.patch_width * np.sqrt(self.batch_size), 3),
                       image_np.shape)

  def testGetConfusionMatrix(self):
    predicted_probabilities = np.array([[0.4, 0.6], [0, 1]])
    confusion_matrix = miq_eval.get_confusion_matrix(
        predicted_probabilities, [0, 1],
        os.path.join(self.test_dir, 'confusion_matrix.png'),
        'Test confusion matrix',
        use_predictions_instead_of_probabilities=True)
    confusion_matrix_expected = np.array([[0.0, 1.0], [0.0, 1.0]])
    self.assertAllEqual(confusion_matrix_expected, confusion_matrix)

  def testGetConfusionMatrixWithProbabilities(self):
    predicted_probabilities = np.array([[0.4, 0.6], [0, 1]])
    confusion_matrix = miq_eval.get_confusion_matrix(
        predicted_probabilities, [0, 1],
        os.path.join(self.test_dir, 'confusion_matrix_probabilities.png'),
        'Test confusion matrix with probabilities',
        use_predictions_instead_of_probabilities=False)
    confusion_matrix_expected = np.array([[0.4, 0.6], [0, 1]], dtype=np.float32)
    self.assertAllEqual(confusion_matrix_expected, confusion_matrix)

  def testGetAggregatedPredictionTruePositive1(self):
    with self.test_session() as sess:
      probabilities = tf.constant(
          [[0.0, 1.0], [0.2, 0.8], [0.5, 0.5], [0.9, 0.1]])
      labels = tf.constant([1, 1, 1, 1])
      prediction, label = miq_eval.get_aggregated_prediction(probabilities,
                                                             labels,
                                                             self.batch_size)

      self.assertEquals(sess.run(label), 1)
      self.assertEquals(sess.run(prediction), 1)

  def testGetAggregatedPredictionTruePositive2(self):
    with self.test_session() as sess:
      probabilities = tf.constant(
          [[0.6, 0.4], [0.6, 0.4], [0.6, 0.4], [0.0, 1.0]])
      labels = tf.constant([1, 1, 1, 1])
      prediction, label = miq_eval.get_aggregated_prediction(probabilities,
                                                             labels,
                                                             self.batch_size)
      self.assertEquals(sess.run(label), 1)
      self.assertEquals(sess.run(prediction), 1)

  def testGetAggregatedPredictionTrueNegative1(self):
    with self.test_session() as sess:
      probabilities = tf.constant(
          [[0.4, 0.6], [0.4, 0.6], [0.4, 0.6], [1.0, 0.0]])
      labels = tf.constant([0, 0, 0, 0])
      prediction, label = miq_eval.get_aggregated_prediction(probabilities,
                                                             labels,
                                                             self.batch_size)
      self.assertEquals(sess.run(label), 0)
      self.assertEquals(sess.run(prediction), 0)

  def testGetAggregatedPredictionTrueNegative2(self):
    with self.test_session() as sess:
      probabilities = tf.constant(
          [[1.0, 0.0], [0.8, 0.2], [0.5, 0.5], [0.1, 0.9]])
      labels = tf.constant([0, 0, 0, 0])
      prediction, label = miq_eval.get_aggregated_prediction(probabilities,
                                                             labels,
                                                             self.batch_size)
      self.assertEquals(sess.run(label), 0)
      self.assertEquals(sess.run(prediction), 0)

  def testGetAggregatedPredictionRequiresIdenticalLabels(self):
    with self.test_session() as sess:
      probabilities = tf.constant(
          [[0.0, 1.0], [0.0, 0.1], [0.0, 0.1], [0.0, 1.0]])
      labels = tf.constant([0, 0, 0, 1])
      _, label = miq_eval.get_aggregated_prediction(probabilities, labels,
                                                    self.batch_size)
      with self.assertRaises(tf.errors.InvalidArgumentError):
        self.assertEquals(sess.run(label), 0)

  def testAggregatedPredictionWithAccuracy(self):
    with self.test_session() as sess:
      probabilities = tf.constant(
          [[1.0, 0.0], [0.8, 0.2], [0.5, 0.5], [0.1, 0.9]])
      labels = tf.constant([0, 0, 0, 0], dtype=tf.int64)
      prediction, label = miq_eval.get_aggregated_prediction(probabilities,
                                                             labels,
                                                             self.batch_size)
      self.assertEquals(sess.run(label), 0)
      self.assertEquals(sess.run(prediction), 0)

      # Check that 'prediction' and 'label' are valid inputs to this function.
      slim.metrics.aggregate_metric_map({
          'Accuracy': tf.contrib.metrics.streaming_accuracy(prediction, label),
      })

  def testVisualizeImagePredictionsRuns(self):
    num_patches = 4
    patches = np.ones((num_patches, 28, 28, 1))
    probabilities = np.ones((num_patches, 2)) / 2.0
    labels = np.ones(num_patches, dtype=np.int32)
    miq_eval.visualize_image_predictions(
        patches,
        probabilities,
        labels,
        self.image_shape[0],
        self.image_shape[1],
        show_plot=True)

  def testGetClassRgbIsHsv(self):
    class_rgb = miq_eval._get_class_rgb(11, 0)
    self.assertEquals(3, len(class_rgb))
    # This is the first HSV color.
    self.assertEquals((1.0, 0, 0), class_rgb)

  def testGetCertainty(self):
    certainty = miq_eval.get_certainty(np.array([0.5, 0.5]))
    self.assertEquals(0.0, certainty)
    certainty = miq_eval.get_certainty(np.array([1.0, 0.0]))
    self.assertEquals(1.0, certainty)

  def testGetRgbImageRuns(self):
    num_rows = 4
    patch_width = 28
    num_patches = num_rows**2
    num_classes = 2
    image_width = patch_width * num_rows
    image = np.ones((image_width, image_width, 1))
    patches = np.ones((num_patches, patch_width, patch_width, 1))
    probabilities = np.ones(
        (num_patches, num_classes), dtype=np.float32) / num_classes
    labels = np.ones(num_patches, dtype=np.int32)

    rgb_image = miq_eval.get_rgb_image(
        np.max(image), patches, probabilities, labels,
        (image_width, image_width))
    self.assertEquals(rgb_image.shape, (image_width, image_width, 3))

    # Check function runs with all probabilities set to 0, without
    # divide-by-zero issues.

    probabilities = np.zeros(
        (num_patches, num_classes), dtype=np.float32) / num_classes

    rgb_image = miq_eval.get_rgb_image(
        np.max(image), patches, probabilities, labels,
        (image_width, image_width))
    self.assertEquals(rgb_image.shape, (image_width, image_width, 3))

  def testAggregatePredictionFromProbabilities(self):
    probabilities = np.array([[1.0 / 3, 1.0 / 3, 1.0 / 3], [0.0, 0.2, 0.8]])

    (predicted_class, certainties, probabilities_averaged
    ) = miq_eval.aggregate_prediction_from_probabilities(probabilities)
    self.assertEquals(2, predicted_class)
    np.testing.assert_allclose(
        np.array([0.0, 0.2, 0.8]), probabilities_averaged, atol=1e-3)
    expected_certainties = {
        'mean': np.float64(0.272),
        'max': np.float64(0.545),
        'aggregate': np.float64(0.545),
        'weighted': np.float64(0.545)
    }
    self.assertDictEqual(expected_certainties, certainties)

  def testAggregatePredictionFromProbabilitiesLeastCertain(self):
    probabilities = np.ones((2, 3)) / 3.0
    (predicted_class, certainties, probabilities_averaged
    ) = miq_eval.aggregate_prediction_from_probabilities(probabilities)
    self.assertEquals(0, predicted_class)
    np.testing.assert_allclose(
        np.array([1.0 / 3, 1.0 / 3, 1.0 / 3]),
        probabilities_averaged,
        atol=1e-3)
    expected_certainties = {
        'mean': np.float64(0.0),
        'max': np.float64(0.0),
        'aggregate': np.float64(0.0),
        'weighted': np.float64(0.0)
    }
    self.assertDictEqual(expected_certainties, certainties)

  def testAggregatePredictionFromProbabilitiesMostCertain(self):
    probabilities = np.array([[1.0 / 3, 1.0 / 3, 1.0 / 3], [0.0, 0.0, 1.0]])
    (predicted_class, certainties, probabilities_averaged
    ) = miq_eval.aggregate_prediction_from_probabilities(probabilities)
    self.assertEquals(2, predicted_class)
    np.testing.assert_allclose(
        np.array([0, 0, 1.0]), probabilities_averaged, atol=1e-3)
    expected_certainties = {
        'mean': np.float64(0.5),
        'max': np.float64(1.0),
        'aggregate': np.float64(1.0),
        'weighted': np.float64(1.0)
    }
    self.assertDictEqual(expected_certainties, certainties)

  def testAggregatePredictionFromProbabilitiesWithProduct(self):
    probabilities = np.array([[0.25, 0.25, 0.5], [0.1, 0.2, 0.7]])
    probabilities_aggregated = miq_eval.aggregate_prediction_from_probabilities(
        probabilities, miq_eval.METHOD_PRODUCT).probabilities
    expected = probabilities[0, :] * probabilities[1, :]
    expected /= expected.sum()
    np.testing.assert_allclose(
        np.array(expected), probabilities_aggregated, atol=1e-3)

  def testAggregatePredictionFromProbabilitiesWithProduct2(self):
    probabilities = np.array(
        [[0.25, 0.25, 0.5], [0.1, 0.2, 0.7], [0.4, 0.3, 0.3]])
    probabilities_aggregated = miq_eval.aggregate_prediction_from_probabilities(
        probabilities, miq_eval.METHOD_PRODUCT).probabilities
    np.testing.assert_allclose(
        np.array([0.077, 0.115, 0.807]), probabilities_aggregated, atol=1e-3)

  def testAddRgbAnnotation(self):
    image = np.zeros((20, 20, 3))
    predicted_rgb = (1, 0, 0)
    actual_rgb = (0, 1, 0)
    max_value = 1
    image_rgb = miq_eval._add_rgb_annotation(image, predicted_rgb, actual_rgb,
                                             max_value)
    image_expected = np.zeros((20, 20, 3))
    image_expected[0:miq_eval.BORDER_SIZE, :, 1] = 1
    image_expected[-1 * miq_eval.BORDER_SIZE:, :, 0] = 1
    np.testing.assert_array_equal(image_rgb, image_expected)

  def testPatchesToImageNonSquare(self):
    num_rows = 2
    num_cols = 3
    num_patches = num_rows * num_cols
    patch_width = 28
    image_shape = patch_width * num_rows, patch_width * num_cols
    patches = np.ones((num_patches, patch_width, patch_width, 1))
    image = miq_eval._patches_to_image(patches, image_shape)
    self.assertEquals(image.shape, (image_shape[0], image_shape[1], 1))

    with self.assertRaises(ValueError):
      image_shape_invalid = (20, 20)
      miq_eval._patches_to_image(patches, image_shape_invalid)

  def testSetBorderPixels(self):
    image = np.zeros((5, 5, 1))
    image_expected = np.ones((5, 5, 1))
    image_expected[2, 2, :] = 0
    image_with_border = miq_eval._set_border_pixels(image, value=1)
    np.testing.assert_array_equal(image_with_border, image_expected)

  def testApplyImageGamma(self):
    image = np.array([1.0, 2.0])
    image_original = np.copy(image)
    image_with_gamma = miq_eval.apply_image_gamma(image, gamma=0.5)

    # Check original image is unmodified.
    np.testing.assert_array_equal(image, image_original)

    # Check gamma has been applied
    image_expected = np.array([0.5, 2.0])
    np.testing.assert_array_equal(image_with_gamma, image_expected)

  def testGetModelAndMetricsWithoutTrueLabels(self):
    g = tf.Graph()
    with g.as_default():
      images = tf.zeros(
          [self.batch_size, self.patch_width, self.patch_width, 1])
      num_classes = 11
      one_hot_labels = tf.zeros([self.batch_size, num_classes])
      labels = miq_eval.get_model_and_metrics(images, num_classes,
                                              one_hot_labels, False).labels

      sv = tf.train.Supervisor()
      with sv.managed_session() as sess:
        [labels_np] = sess.run([labels])

      self.assertTrue(np.all(-1 == labels_np))

  def testGetModelAndMetricsWithTrueLabels(self):
    g = tf.Graph()
    with g.as_default():
      batch_size = 2
      images = tf.zeros([batch_size, self.patch_width, self.patch_width, 1])
      one_hot_labels = tf.constant([0, 1, 0, 1], dtype=tf.float32, shape=(2, 2))

      num_classes = 11
      labels = miq_eval.get_model_and_metrics(images, num_classes,
                                              one_hot_labels, False).labels

      sv = tf.train.Supervisor()
      with sv.managed_session() as sess:
        [labels_np] = sess.run([labels])

      self.assertTrue(np.all(1 == labels_np))

  def testSaveInferenceResultsRuns(self):
    num_classes = 3
    aggregate_probabilities = np.ones((self.batch_size, num_classes))
    aggregate_labels = range(self.batch_size)
    certainties = {}
    certainties['mean'] = [0.5] * self.batch_size
    certainties['max'] = [0.8] * self.batch_size
    certainties['aggregate'] = [0.9] * self.batch_size
    certainties['weighted'] = [1.0] * self.batch_size
    orig_names = ['orig_name'] * self.batch_size
    aggregate_predictions = range(self.batch_size)
    output_path = os.path.join(self.test_dir, 'results.csv')
    miq_eval.save_inference_results(aggregate_probabilities, aggregate_labels,
                                    certainties, orig_names,
                                    aggregate_predictions, output_path)

  def testSaveAndLoadResults(self):
    num_classes = 3
    aggregate_probabilities = np.ones((self.batch_size, num_classes))
    aggregate_probabilities[0, 2] = 3
    aggregate_labels = range(self.batch_size)
    certainties = {}
    certainties['mean'] = [np.float64(1.0 / 3)] * self.batch_size
    certainties['max'] = [0.0] * self.batch_size
    certainties['aggregate'] = [0.9] * self.batch_size
    certainties['weighted'] = [1.0] * self.batch_size
    orig_names = ['orig_name'] * self.batch_size
    aggregate_predictions = range(self.batch_size)
    test_directory = os.path.join(self.test_dir, 'save_load_test')
    os.makedirs(test_directory)
    output_path = os.path.join(test_directory, 'results.csv')
    miq_eval.save_inference_results(aggregate_probabilities, aggregate_labels,
                                    certainties, orig_names,
                                    aggregate_predictions, output_path)

    (aggregate_probabilities_2, aggregate_labels_2, certainties_2, orig_names_2,
     aggregate_predictions_2) = miq_eval.load_inference_results(test_directory)
    np.testing.assert_array_equal(aggregate_probabilities,
                                  aggregate_probabilities_2)
    self.assertEquals(aggregate_labels, aggregate_labels_2)
    self.assertEquals(certainties['mean'], certainties_2['mean'])
    self.assertEquals(certainties['max'], certainties_2['max'])
    self.assertEquals(certainties['aggregate'], certainties_2['aggregate'])
    self.assertEquals(certainties['weighted'], certainties_2['weighted'])
    self.assertEquals(orig_names, orig_names_2)
    self.assertEquals(aggregate_predictions, aggregate_predictions_2)

  def testSaveResultPlotsRuns(self):
    num_classes = 4
    aggregate_probabilities = np.ones((self.batch_size, num_classes))
    aggregate_labels = range(self.batch_size)
    miq_eval.save_result_plots(
        aggregate_probabilities,
        aggregate_labels,
        save_confusion=True,
        output_directory=self.test_dir)
    miq_eval.save_result_plots(
        aggregate_probabilities,
        aggregate_labels,
        save_confusion=False,
        output_directory=self.test_dir)

  def testSavePredictionHistogramRuns(self):
    probabilities = np.array(((0.0, 1.0), (0.5, 0.5), (0.2, 0.8)))
    predictions = np.array([0, 1, 0])
    assert probabilities.shape[0] == len(predictions)
    miq_eval.save_prediction_histogram(
        predictions,
        os.path.join(self.test_dir, 'histogram.png'),
        probabilities.shape[1])


if __name__ == '__main__':
  unittest.main()
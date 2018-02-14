# coding=utf-8
# Copyright 2018 The Tensor2Tensor Authors.
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

"""Library for training of RL agent with PPO algorithm."""

from __future__ import absolute_import

import functools

# Dependency imports

import gym


from tensor2tensor import models  # pylint: disable=unused-import
from tensor2tensor.models.research import rl  # pylint: disable=unused-import
from tensor2tensor.rl import collect
from tensor2tensor.rl import ppo
from tensor2tensor.rl.envs import utils

import tensorflow as tf


def define_train(hparams, environment_spec, event_dir):
  """Define the training setup."""
  if isinstance(environment_spec, str):
    env_lambda = lambda: gym.make(environment_spec)
  else:
    env_lambda = environment_spec
  policy_lambda = hparams.network
  env = env_lambda()
  action_space = env.action_space

  batch_env = utils.define_batch_env(env_lambda, hparams.num_agents)

  policy_factory = tf.make_template(
      "network",
      functools.partial(policy_lambda, action_space, hparams))

  with tf.variable_scope("train"):
    memory, collect_summary = collect.define_collect(
      policy_factory, batch_env, hparams, eval_phase=False)
  ppo_summary = ppo.define_ppo_epoch(memory, policy_factory, hparams)
  summary = tf.summary.merge([collect_summary, ppo_summary])

  with tf.variable_scope("eval"):
    eval_env_lambda = env_lambda
    if event_dir and hparams.video_during_eval:
      eval_env_lambda = lambda: gym.wrappers.Monitor(
        env_lambda(), event_dir, video_callable=lambda i: i % 2 == 0)
    wrapped_eval_env_lambda = lambda: utils.EvalVideoWrapper(eval_env_lambda())
    _, eval_summary = collect.define_collect(
      policy_factory,
      utils.define_batch_env(wrapped_eval_env_lambda, hparams.num_eval_agents,
                             xvfb=hparams.video_during_eval),
      hparams, eval_phase=True)
  return summary, eval_summary


def train(hparams, environment_spec, event_dir=None):
  train_summary_op, eval_summary_op = define_train(hparams, environment_spec,
                                                   event_dir)

  if event_dir:
    summary_writer = tf.summary.FileWriter(
        event_dir, graph=tf.get_default_graph(), flush_secs=60)
  else:
    summary_writer = None

  with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())
    for epoch_index in range(hparams.epochs_num):
      summary = sess.run(train_summary_op)
      if summary_writer:
        summary_writer.add_summary(summary, epoch_index)
      if hparams.eval_every_epochs and epoch_index % hparams.eval_every_epochs == 0:
        summary = sess.run(eval_summary_op)
        if summary_writer:
          summary_writer.add_summary(summary, epoch_index)

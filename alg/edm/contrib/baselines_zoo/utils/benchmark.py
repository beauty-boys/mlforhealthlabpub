import argparse
import os
import subprocess

import pytablewriter
import numpy as np
import pandas as pd
import matplotlib
# Fix when running tests
try:
    import tkinter as Tk
except ImportError:
    matplotlib.use('agg')

from stable_baselines.results_plotter import load_results, ts2xy

from utils import get_trained_models

parser = argparse.ArgumentParser()
parser.add_argument('--log-dir', help='Root log folder', default='trained_agents/', type=str)
parser.add_argument('--benchmark-dir', help='Benchmark log folder', default='logs/benchmark/', type=str)
parser.add_argument('-n', '--n-timesteps', help='number of timesteps', default=150000,
                    type=int)
parser.add_argument('--n-envs', help='number of environments', default=1,
                    type=int)
parser.add_argument('--verbose', help='Verbose mode (0: no output, 1: INFO)', default=1,
                    type=int)
parser.add_argument('--seed', help='Random generator seed', type=int, default=0)
parser.add_argument('--test-mode', action='store_true', default=False,
                    help='Do only one experiments (useful for testing)')
args = parser.parse_args()

trained_models = get_trained_models(args.log_dir)
n_experiments = len(trained_models)
results = {
    'algo': [],
    'env_id': [],
    'mean_reward': [],
    'std_reward': [],
    'n_timesteps': [],
    'n_episodes': []
}

for idx, trained_model in enumerate(trained_models.keys()):
    algo, env_id = trained_models[trained_model]
    n_envs = args.n_envs
    n_timesteps = args.n_timesteps
    if algo in ['dqn', 'ddpg', 'sac', 'td3']:
        n_envs = 1
        n_timesteps *= args.n_envs

    # Comment out to becnhmark HER robotics env
    # this requires a mujoco licence
    if 'Fetch' in env_id:
        print("Skipping mujoco env: {}".format(env_id))
        continue

    # Skip old BipedalWalker version
    if 'Walker-v2' in env_id or 'WalkerHardcore-v2' in env_id:
        continue

    reward_log = '{}/{}/'.format(args.benchmark_dir, trained_model)
    arguments = [
        '-n', str(n_timesteps),
        '--n-envs', str(n_envs),
        '-f', args.log_dir,
        '--algo', algo,
        '--env', env_id,
        '--no-render',
        '--seed', str(args.seed),
        '--verbose', '0',
        '--reward-log', reward_log
    ]
    if args.verbose >= 1:
        print('{}/{}'.format(idx + 1, n_experiments))
        print("Evaluating {} on {}...".format(algo, env_id))

    skip_eval = False
    if os.path.isdir(reward_log):
        try:
            x, y = ts2xy(load_results(reward_log), 'timesteps')
            skip_eval = len(x) > 0
        except:
            pass

    if skip_eval:
        print("Skipping eval...")
    else:
        return_code = subprocess.call(['python', 'enjoy.py'] + arguments)
        x, y = ts2xy(load_results(reward_log), 'timesteps')

    if len(x) > 0:
        mean_reward = np.mean(y)
        std_reward = np.std(y)
        results['algo'].append(algo)
        results['env_id'].append(env_id)
        results['mean_reward'].append(mean_reward)
        results['std_reward'].append(std_reward)
        results['n_timesteps'].append(x[-1])
        results['n_episodes'].append(len(y))
        if args.verbose >= 1:
            print(x[-1], 'timesteps')
            print(len(y), "Episodes")
            print("Mean reward: {:.2f} +- {:.2f}".format(mean_reward, std_reward))
            print()
    else:
        print("Not enough timesteps")

    if args.test_mode:
        break

# Create DataFrame
results_df = pd.DataFrame(results)
# Sort results
results_df = results_df.sort_values(by=['algo', 'env_id'])

writer = pytablewriter.MarkdownTableWriter()
writer.from_dataframe(results_df)
# change the output stream to a file
with open("{}/benchmark.md".format(args.benchmark_dir), "w") as f:
    writer.stream = f
    writer.write_table()
print("Results written to:", "{}/benchmark.md".format(args.benchmark_dir))

# Update root benchmark file
with open("benchmark.md", "w") as f:
    writer.stream = f
    writer.write_table()

# Alternatively, to dump as csv file:
# results_df.to_csv('{}/benchmark.csv'.format(args.benchmark_dir), sep=",", index=False)
# print("Saved results to {}/benchmark.csv".format(args.benchmark_dir))

import argparse
import dill
import jax
import numpy as np

import pomdp
pomdp.horizon = 25


parser = argparse.ArgumentParser()
parser.add_argument('--silent', action='store_true')
parser.add_argument('-i', type=int, default=0)
parser.add_argument('-n', type=int, default=5)
parser.add_argument('--cont', action='store_true')
args = parser.parse_args()

key = jax.random.PRNGKey(0)

###
S = 3
A = 2
Z = 12
with open('data/adni.obj', 'rb') as f:
    data = dill.load(f)
    data = data[:len(data)*args.i//args.n] + data[len(data)*(args.i+1)//args.n:]


def log_pi(alp, bet, b):
    res = np.zeros(A)
    for a in range(A):
        if alp[a].size == 0:
            res[a] = -1e6
        else:
            res[a] = bet * (alp[a] @ b).max()
    return res - np.log(np.sum(np.exp(res)))

def likelihood(b0, T, O, alp):
    res = 0
    for traj in data:
        b = b0
        for a, z in zip(traj['a'], traj['z']):
            res += log_pi(alp, 1, b)[a]
            b = O[a,:,z] * (T[:,a,:].T @ b)
            b /= b.sum()
    return res


if args.cont:

    with open('res/adni/res{}-poirl.obj'.format(args.i), 'rb') as f:
        res = dill.load(f)
        key = res['key']
        b0, T, O, R = res['out'][-1]

else:

    res = dict()
    res['out'] = list()

    key, *subkey = jax.random.split(key, 4)
    b0 = np.array(jax.random.dirichlet(subkey[0], np.ones(S)))
    T = np.array(jax.random.dirichlet(subkey[1], np.ones((S,A,S)), shape=(S,A)))
    O = np.array(jax.random.dirichlet(subkey[1], np.ones((A,S,Z)), shape=(A,S)))

    ###
    O[0,:,(1,2,3,5,6,7,9,10,11)] = np.zeros((S,9)).T
    O[1,:,(0,4,8)] = np.zeros((S,3)).T
    O /= O.sum(axis=-1, keepdims=True)

    for i in range(1000):
        _b0 = np.zeros(b0.shape)
        _T = np.zeros(T.shape)
        _O = np.zeros(O.shape)

        for traj in data:

            alp = [None] * (traj['tau']+1)
            alp[0] = b0
            for t in range(traj['tau']):
                alp[t+1] = O[traj['a'][t],:,traj['z'][t]] * (T[:,traj['a'][t],:].T @ alp[t])
                alp[t+1] /= alp[t+1].sum()

            bet = [None] * (traj['tau']+1)
            bet[-1] = np.ones(S)
            for t in reversed(range(traj['tau'])):
                bet[t] = T[:,traj['a'][t],:] @ (O[traj['a'][t],:,traj['z'][t]] * bet[t+1])
                bet[t] /= bet[t].sum()

            gmm = [None] * (traj['tau']+1)
            for t in range(traj['tau']+1):
                gmm[t] = alp[t] * bet[t]
                gmm[t] /= gmm[t].sum()

            xi = [None] * traj['tau']
            for t in range(traj['tau']):
                xi[t] = T[:,traj['a'][t],:] * O[None,traj['a'][t],:,traj['z'][t]] * (alp[t][:,None] @ bet[t+1][None,:])
                xi[t] /= xi[t].sum()

            _b0 += gmm[0]
            for t in range(traj['tau']):
                _O[traj['a'][t],:,traj['z'][t]] += gmm[t+1]
            for t in range(traj['tau']):
                _T[:,traj['a'][t],:] += xi[t]

        _b0 /= _b0.sum()
        _T /= _T.sum(axis=-1, keepdims=True)
        _O /= _O.sum(axis=-1, keepdims=True)

        diff = max(np.abs(_b0-b0).max(), np.abs(_T-T).max(), np.abs(_O-O).max())
        b0, T, O = _b0, _T, _O

        if not args.silent:
            print('i = {}, diff = {}'.format(i, diff))
            if diff < 1e-6:
                break

    ###
    key, subkey = jax.random.split(key)
    R = np.zeros((S,A))
    R += .001 * np.array(jax.random.normal(subkey, shape=(S,A)))

alp = pomdp.solve(S, A, Z, b0, T, O, R)
like = likelihood(b0, T, O, alp)

rtio = 0
rtio_n = 0
for i in range(len(res['out']), 1000):

    key, subkey = jax.random.split(key)
    _R = R + .001 * np.array(jax.random.normal(subkey, shape=(S,A)))
    _alp = pomdp.solve(S, A, Z, b0, T, O, _R)
    _like = likelihood(b0, T, O, _alp)

    key, subkey = jax.random.split(key)
    unif = jax.random.uniform(subkey)
    if np.log(unif) < _like - like:
        R = _R
        like = _like

    rtio += 1 if like == _like else 0
    rtio_n += 1
    if not args.silent:
        print('i = {}, like = {}, {} ({})'.format(i, like, '*' if like == _like else '-', rtio / rtio_n))

    res['key'] = key
    res['out'].append((b0, T, O, R))
    if (i+1) % 100 == 0:
        with open('res/adni/res{}-poirl.obj'.format(args.i), 'wb') as f:
            dill.dump(res, f)

with open('res/adni/res{}-poirl.obj'.format(args.i), 'wb') as f:
    dill.dump(res, f)

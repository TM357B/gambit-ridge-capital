"""Nelder-Mead (simplexe) en numpy : calibrages sans gradient (vraisemblances bruitées, hyperparamètres)."""

from __future__ import annotations

import numpy as np


def nelder_mead(f, x0, pas=0.3, iter_max=300, tol=1e-6):
    """Minimise f à partir de x0. Renvoie (x, f(x), nombre d'évaluations)."""
    x0 = np.asarray(x0, dtype=float)
    n = len(x0)
    simplexe = [x0] + [x0 + pas * np.eye(n)[i] for i in range(n)]
    valeurs = [f(x) for x in simplexe]
    evals = n + 1
    for _ in range(iter_max):
        ordre = np.argsort(valeurs)
        simplexe = [simplexe[i] for i in ordre]
        valeurs = [valeurs[i] for i in ordre]
        if abs(valeurs[-1] - valeurs[0]) < tol * (1 + abs(valeurs[0])):
            break
        centre = np.mean(simplexe[:-1], axis=0)
        xr = centre + (centre - simplexe[-1])
        fr = f(xr); evals += 1
        if fr < valeurs[0]:
            xe = centre + 2 * (centre - simplexe[-1])
            fe = f(xe); evals += 1
            simplexe[-1], valeurs[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < valeurs[-2]:
            simplexe[-1], valeurs[-1] = xr, fr
        else:
            xc = centre + 0.5 * (simplexe[-1] - centre)
            fc = f(xc); evals += 1
            if fc < valeurs[-1]:
                simplexe[-1], valeurs[-1] = xc, fc
            else:  # rétrécissement vers le meilleur point
                simplexe = [simplexe[0]] + [simplexe[0] + 0.5 * (x - simplexe[0]) for x in simplexe[1:]]
                valeurs = [valeurs[0]] + [f(x) for x in simplexe[1:]]
                evals += n
    i = int(np.argmin(valeurs))
    return simplexe[i], float(valeurs[i]), evals

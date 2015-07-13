#-*- coding: utf-8 -*-
#
# Copyright 2015 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

"""
It contains functions to predict the A/T gear shifting.
"""

__author__ = 'Vincenzo Arcidiacono'

from collections import OrderedDict
from itertools import chain, repeat

import numpy as np
from scipy.optimize import fmin
from scipy.interpolate import InterpolatedUnivariateSpline
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import mean_absolute_error
from compas.dispatcher.utils import pairwise
from compas.functions.utils import median_filter, grouper, \
    interpolate_cloud, clear_gear_fluctuations

from compas.functions.constants import *
from compas.functions.gear_box import calculate_gear_box_speeds_in
from compas.functions.wheels import calculate_wheel_powers

def get_full_load(fuel_type):
    """
    Returns vehicle full load curve.

    :param fuel_type:
        Vehicle fuel type (diesel or gas).
    :type fuel_type: str

    :return:
        Vehicle full load curve.
    :rtype: InterpolatedUnivariateSpline
    """

    full_load = {
        'gas': InterpolatedUnivariateSpline(
            np.linspace(0, 1.2, 13),
            [0.1, 0.198238659, 0.30313392, 0.410104642, 0.516920841,
             0.621300767, 0.723313491, 0.820780368, 0.901750158, 0.962968496,
             0.995867804, 0.953356174, 0.85]),
        'diesel': InterpolatedUnivariateSpline(
            np.linspace(0, 1.2, 13),
            [0.1, 0.278071182, 0.427366185, 0.572340499, 0.683251935,
             0.772776746, 0.846217049, 0.906754984, 0.94977083, 0.981937981,
             1, 0.937598144, 0.85])
    }
    return full_load[fuel_type]


def identify_gear(
        ratio, velocity, acceleration, idle_engine_speed, vsr, max_gear):
    """
    Identifies a gear.

    :param ratio:
        Vehicle velocity speed ratio.
    :type ratio: float

    :param velocity:
        Vehicle velocity.
    :type velocity: float

    :param acceleration:
        Vehicle acceleration.
    :type acceleration: float

    :param idle_engine_speed:
        Engine speed idle.
    :type idle_engine_speed: (float, float)

    :param vsr:
        Constant velocity speed ratios of the gear box.
    :type vsr: iterable

    :return:
        A gear.
    :rtype: int
    """

    if velocity <= VEL_EPS:
        return 0

    m, (gear, vs) = min((abs(v - ratio), (k, v)) for k, v in vsr)

    if (acceleration < 0
        and (velocity <= idle_engine_speed[0] * vs
             or abs(velocity / idle_engine_speed[1] - ratio) < m)):
        return 0

    if velocity > VEL_EPS and acceleration > 0 and gear == 0:
        return 1

    return gear


def identify_gears(
        times, velocities, accelerations, gear_box_speeds,
        velocity_speed_ratios, idle_engine_speed=(0.0, 0.0)):
    """
    Identifies gear time series.

    :param times:
        Time vector.
    :type times: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :param accelerations:
        Acceleration vector.
    :type accelerations: np.array, float

    :param gear_box_speeds:
        Gear box speed vector.
    :type gear_box_speeds: np.array

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :param idle_engine_speed:
        Engine speed idle median and std.
    :type idle_engine_speed: (float, float), optional

    :return:
        Gear vector identified.
    :rtype: np.array
    """

    vsr = [v for v in velocity_speed_ratios.items()]

    ratios = velocities / gear_box_speeds

    ratios[gear_box_speeds < MIN_ENGINE_SPEED] = 0

    idle_speed = (idle_engine_speed[0] - idle_engine_speed[1],
                  idle_engine_speed[0] + idle_engine_speed[1])

    max_gear = max(velocity_speed_ratios)

    it = (ratios, velocities, accelerations, repeat(idle_speed), repeat(vsr),
          repeat(max_gear))

    gear = list(map(identify_gear, *it))

    gear = median_filter(times, gear, TIME_WINDOW)
    gear = clear_gear_fluctuations(times, gear, TIME_WINDOW)

    speeds = calculate_gear_box_speeds_in(gear, velocities, velocity_speed_ratios)
    return gear, speeds


def correct_gear_upper_bound_engine_speed(
        velocity, acceleration, gear, velocity_speed_ratios, max_gear,
        upper_bound_engine_speed):
    """
    Corrects the gear predicted according to upper bound engine speed.

    :param velocity:
        Vehicle velocity.
    :type velocity: float

    :param acceleration:
        Vehicle acceleration.
    :type acceleration: float

    :param gear:
        Predicted vehicle gear.
    :type gear: int

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :param max_gear:
        Maximum gear.
    :type max_gear: int

    :param upper_bound_engine_speed:
        Upper bound engine speed.
    :type upper_bound_engine_speed: float

    :return:
        A gear corrected according to upper bound engine speed.
    :rtype: int
    """

    if abs(acceleration) < ACC_EPS and velocity > VEL_EPS:

        l = velocity / upper_bound_engine_speed

        while velocity_speed_ratios[gear] < l and gear < max_gear:
            gear += 1

    return gear


def correct_gear_full_load(
        velocity, acceleration, gear, velocity_speed_ratios, max_engine_power,
        max_engine_speed_at_max_power, idle_engine_speed, full_load_curve,
        road_loads, inertia, min_gear):
    """
    Corrects the gear predicted according to full load curve.

    :param velocity:
        Vehicle velocity.
    :type velocity: float

    :param acceleration:
        Vehicle acceleration.
    :type acceleration: float

    :param gear:
        Predicted vehicle gear.
    :type gear: int

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :param max_engine_power:
        Maximum power.
    :type max_engine_power: float

    :param max_engine_speed_at_max_power:
        Rated engine speed.
    :type max_engine_speed_at_max_power: float

    :param idle_engine_speed:
        Engine speed idle median and std.
    :type idle_engine_speed: (float, float)

    :param full_load_curve:
        Vehicle full load curve.
    :type full_load_curve: InterpolatedUnivariateSpline

    :param road_loads:
        Cycle road loads.
    :type road_loads: list, tuple

    :param inertia:
        Cycle inertia.
    :type inertia: float

    :return:
        A gear corrected according to full load curve.
    :rtype: int
    """
    if velocity > 100:
        return gear

    p_norm = calculate_wheel_powers(velocity, acceleration, road_loads, inertia)
    p_norm /= max_engine_power

    r = velocity / (max_engine_speed_at_max_power - idle_engine_speed[0])

    vsr = velocity_speed_ratios
    flc = full_load_curve

    while gear > min_gear and (gear not in vsr or p_norm > flc(r / vsr[gear])):
        # to consider adding the reverse function in the future because the
        # n+200 rule should be applied at the engine not the GB
        # (rpm < idle_speed + 200 and 0 <= a < 0.1) or
        gear -= 1

    return gear


def correct_gear_v0(
        velocity_speed_ratios, upper_bound_engine_speed, max_engine_power,
        max_engine_speed_at_max_power, idle_engine_speed, full_load_curve,
        road_loads, inertia):
    """
    Returns a function to correct the gear predicted according to
    :func:`compas.functions.AT_gear.correct_gear_upper_bound_engine_speed`
    and :func:`compas.functions.AT_gear.correct_gear_full_load`.

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :param upper_bound_engine_speed:
        Upper bound engine speed.
    :type upper_bound_engine_speed: float

    :param max_engine_power:
        Maximum power.
    :type max_engine_power: float

    :param max_engine_speed_at_max_power:
        Rated engine speed.
    :type max_engine_speed_at_max_power: float

    :param idle_engine_speed:
        Engine speed idle median and std.
    :type idle_engine_speed: (float, float)

    :param full_load_curve:
        Vehicle full load curve.
    :type full_load_curve: InterpolatedUnivariateSpline

    :param road_loads:
        Cycle road loads.
    :type road_loads: list, tuple

    :param inertia:
        Cycle inertia.
    :type inertia: float

    :return:
        A function to correct the predicted gear.
    :rtype: function
    """

    max_gear = max(velocity_speed_ratios)
    min_gear = min(velocity_speed_ratios)

    def correct_gear(velocity, acceleration, gear):
        g = correct_gear_upper_bound_engine_speed(
            velocity, acceleration, gear, velocity_speed_ratios, max_gear,
            upper_bound_engine_speed)

        return correct_gear_full_load(
            velocity, acceleration, g, velocity_speed_ratios, max_engine_power,
            max_engine_speed_at_max_power, idle_engine_speed, full_load_curve,
            road_loads, inertia, min_gear)

    return correct_gear


def correct_gear_v1(velocity_speed_ratios, upper_bound_engine_speed):
    """
    Returns a function to correct the gear predicted according to
    :func:`compas.functions.AT_gear.correct_gear_upper_bound_engine_speed`.

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :param upper_bound_engine_speed:
        Upper bound engine speed.
    :type upper_bound_engine_speed: float

    :return:
        A function to correct the predicted gear.
    :rtype: function
    """

    max_gear = max(velocity_speed_ratios)

    def correct_gear(velocity, acceleration, gear):
        return correct_gear_upper_bound_engine_speed(
            velocity, acceleration, gear, velocity_speed_ratios, max_gear,
            upper_bound_engine_speed)

    return correct_gear


def correct_gear_v2(
        velocity_speed_ratios, max_engine_power, max_engine_speed_at_max_power,
        idle_engine_speed, full_load_curve, road_loads, inertia):
    """
    Returns a function to correct the gear predicted according to
    :func:`compas.functions.AT_gear.correct_gear_full_load`.

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :param max_engine_power:
        Maximum power.
    :type max_engine_power: float

    :param max_engine_speed_at_max_power:
        Rated engine speed.
    :type max_engine_speed_at_max_power: float

    :param idle_engine_speed:
        Engine speed idle median and std.
    :type idle_engine_speed: (float, float)

    :param full_load_curve:
        Vehicle full load curve.
    :type full_load_curve: InterpolatedUnivariateSpline

    :param road_loads:
        Cycle road loads.
    :type road_loads: list, tuple

    :param inertia:
        Cycle inertia.
    :type inertia: float

    :return:
        A function to correct the predicted gear.
    :rtype: function
    """

    min_gear = min(velocity_speed_ratios)

    def correct_gear(velocity, acceleration, gear):
        return correct_gear_full_load(
            velocity, acceleration, gear, velocity_speed_ratios,
            max_engine_power, max_engine_speed_at_max_power, idle_engine_speed,
            full_load_curve, road_loads, inertia, min_gear)

    return correct_gear


def correct_gear_v3():
    """
    Returns a function that does not correct the gear predicted.

    :return:
        A function to correct the predicted gear.
    :rtype: function
    """

    def correct_gear(velocity, acceleration, gear):
        return gear

    return correct_gear


def identify_gear_shifting_velocity_limits(gears, velocities):
    """
    Identifies gear shifting velocity matrix.

    :param gears:
        Gear vector.
    :type gears: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :return:
        Gear shifting velocity matrix.
    :rtype: dict
    """

    limits = {}

    for v, (g0, g1) in zip(velocities, pairwise(gears)):
        if v >= VEL_EPS and g0 != g1:
            limits[g0] = limits.get(g0, [[], []])
            limits[g0][g0 < g1].append(v)

    def rjt_out(x, default):
        if x:
            x = np.asarray(x)

            # noinspection PyTypeChecker
            m, (n, s) = np.median(x), (len(x), 1 / np.std(x))

            y = 2 > (abs(x - m) * s)

            if y.any():
                y = x[y]

                # noinspection PyTypeChecker
                m, (n, s) = np.median(y), (len(y), 1 / np.std(y))

            return m, (n, s)
        else:
            return default

    max_gear = max(limits)
    gsv = OrderedDict()
    for k in range(max_gear + 1):
        v0, v1 = limits.get(k, [[], []])
        gsv[k] = [rjt_out(v0, (-1, (0, 0))), rjt_out(v1, (INF, (0, 0)))]

    return correct_gsv(gsv)


def correct_gsv_for_constant_velocities(gsv):
    """
    Corrects the gear shifting matrix velocity according to the NEDC velocities.

    :param gsv:
        Gear shifting velocity matrix.
    :type gsv: dict

    :return:
        A gear shifting velocity matrix corrected from NEDC velocities.
    :rtype: dict
    """

    up_cns_vel = [15, 32, 50, 70]
    up_limit = 3.5
    up_delta = -0.5
    down_cns_vel = [35, 50]
    down_limit = 3.5
    down_delta = -1

    def set_velocity(velocity, const_steps, limit, delta):
        for v in const_steps:
            if v < velocity < v + limit:
                return v + delta
        return velocity

    def fun(v):
        limits = (set_velocity(v[0], down_cns_vel, down_limit, down_delta),
                  set_velocity(v[1], up_cns_vel, up_limit, up_delta))
        return limits

    return {k: fun(v) for k, v in gsv.items()}


def calibrate_gear_shifting_cmv(
        correct_gear, gears, engine_speeds, velocities, accelerations,
        velocity_speed_ratios):
    """
    Calibrates a corrected matrix velocity to predict gears.

    :param gears:
        Gear vector.
    :type gears: np.array

    :param engine_speeds:
        Engine speed vector.
    :type engine_speeds: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :param accelerations:
        Acceleration vector.
    :type accelerations: np.array, float

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :returns:
        A corrected matrix velocity to predict gears.
    :rtype: dict
    """

    gsv = identify_gear_shifting_velocity_limits(gears, velocities)

    gear_id, velocity_limits = zip(*list(gsv.items())[1:])

    def update_gvs(vel_limits):
        gsv[0] = (0, vel_limits[0])

        limits = np.append(vel_limits[1:], float('inf'))
        gsv.update(dict(zip(gear_id, grouper(limits, 2))))

    def error_fun(vel_limits):
        update_gvs(vel_limits)

        g_pre = prediction_gears_gsm(
            correct_gear, gsv, velocities, accelerations)

        speed_predicted = calculate_gear_box_speeds_in(
            g_pre, velocities, velocity_speed_ratios)

        return mean_absolute_error(engine_speeds, speed_predicted)

    x0 = [gsv[0][1]].__add__(list(chain(*velocity_limits))[:-1])

    x = fmin(error_fun, x0)

    update_gvs(x)

    return correct_gsv_for_constant_velocities(gsv)


def calibrate_gear_shifting_cmv_hot_cold(
        correct_gear, times, gears, engine_speeds, velocities, accelerations,
        velocity_speed_ratios, time_cold_hot_transition):
    """
    Calibrates a corrected matrix velocity for cold and hot phases to predict
    gears.

    :param gears:
        Gear vector.
    :type gears: np.array

    :param engine_speeds:
        Engine speed vector.
    :type engine_speeds: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :param accelerations:
        Acceleration vector.
    :type accelerations: np.array, float

    :param velocity_speed_ratios:
        Constant velocity speed ratios of the gear box.
    :type velocity_speed_ratios: dict

    :param idle_engine_speed:
        Engine speed idle median and std.
    :type idle_engine_speed: (float, float)

    :param time_cold_hot_transition:
        Time at cold hot transition phase.
    :type time_cold_hot_transition: float

    :returns:
        Two corrected matrix velocities for cold and hot phases.
    :rtype: dict
    """

    cmv = {}

    b = times <= time_cold_hot_transition

    for i in ['cold', 'hot']:
        cmv[i] = calibrate_gear_shifting_cmv(
            correct_gear, gears[b], engine_speeds[b], velocities[b],
            accelerations[b], velocity_speed_ratios)
        b = np.logical_not(b)

    return cmv


def calibrate_gear_shifting_decision_tree(gears, *params):
    """
    Calibrates a decision tree classifier to predict gears.

    :param gears:
        Gear vector.
    :type gears: np.array

    :param params:
        Time series vectors.
    :type params: (np.array, ...)

    :returns:
        A decision tree classifier to predict gears.
    :rtype: DecisionTreeClassifier
    """

    previous_gear = [gears[0]]

    previous_gear.extend(gears[:-1])

    tree = DecisionTreeClassifier(random_state=0)

    tree.fit(list(zip(previous_gear, *params)), gears)

    return tree


def correct_gsv(gsv):
    """
    Corrects gear shifting velocity matrix from unreliable limits.

    :param gsv:
        Gear shifting velocity matrix.
    :type gsv: dict

    :return:
        Gear shifting velocity matrix corrected from unreliable limits.
    :rtype: dict
    """

    gsv[0] = [0, (VEL_EPS, (INF, 0))]

    for v0, v1 in pairwise(gsv.values()):
        up0, down1 = (v0[1][0], v1[0][0])

        if down1 + VEL_EPS <= v0[0]:
            v0[1] = v1[0] = up0
        elif up0 >= down1:
            v0[1], v1[0] = (up0, down1)
            continue
        elif v0[1][1] >= v1[0][1]:
            v0[1] = v1[0] = up0
        else:
            v0[1] = v1[0] = down1

        v0[1] += VEL_EPS

    gsv[max(gsv)][1] = INF

    return gsv


def calibrate_gspv(gears, velocities, wheel_powers):
    """
    Identifies gear shifting power velocity matrix.

    :param gears:
        Gear vector.
    :type gears: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :param wheel_powers:
        Power at wheels vector.
    :type wheel_powers: np.array

    :return:
        Gear shifting power velocity matrix.
    :rtype: dict
    """
    gspv = {}

    for v, p, (g0, g1) in zip(velocities, wheel_powers, pairwise(gears)):
        if v > VEL_EPS and g0 != g1:
            x = gspv.get(g0, [[], [[], []]])
            if g0 < g1 and p >= 0:
                x[1][0].append(p)
                x[1][1].append(v)
            elif g0 > g1 and p <= 0:
                x[0].append(v)
            else:
                continue
            gspv[g0] = x

    gspv[0] = [[0], [[None], [VEL_EPS]]]

    gspv[max(gspv)][1] = [[0, 1], [INF] * 2]

    for k, v in gspv.items():

        v[0] = InterpolatedUnivariateSpline([0, 1], [np.mean(v[0])] * 2, k=1)

        if len(v[1][0]) > 2:
            v[1] = interpolate_cloud(*v[1])
        else:
            v[1] = [np.mean(v[1][1])] * 2
            v[1] = InterpolatedUnivariateSpline([0, 1], v[1], k=1)

    return gspv


def calibrate_gspv_hot_cold(
        times, gears, velocities, wheel_powers, time_cold_hot_transition):
    """
    Identifies gear shifting power velocity matrices for cold and hot phases.

    :param times:
        Time vector.
    :type times: np.array

    :param gears:
        Gear vector.
    :type gears: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :param wheel_powers:
        Power at wheels vector.
    :type wheel_powers: np.array

    :param time_cold_hot_transition:
        Time at cold hot transition phase.
    :type time_cold_hot_transition: float

    :return:
        Gear shifting power velocity matrices for cold and hot phases.
    :rtype: dict
    """

    gspv = {}

    b = times <= time_cold_hot_transition

    for i in ['cold', 'hot']:
        gspv[i] = calibrate_gspv(gears[b], velocities[b], wheel_powers[b])
        b = np.logical_not(b)

    return gspv


def prediction_gears_decision_tree(correct_gear, decision_tree, times, *params):
    """
    Predicts gears with a decision tree classifier.

    :param correct_gear:
        A function to correct the gear predicted.
    :type correct_gear: function

    :param decision_tree:
        A decision tree classifier to predict gears.
    :type decision_tree: DecisionTreeClassifier

    :param times:
        Time vector.
    :type times: np.array

    :param params:
        Time series vectors.
    :type params: (nx.array, ...)

    :return:
        Predicted gears.
    :rtype: np.array
    """

    gear = [MIN_GEAR]

    predict = decision_tree.predict

    def predict_gear(*args):
        g = predict(gear.__add__(list(args)))[0]
        gear[0] = correct_gear(args[0], args[1], g)
        return gear[0]

    gear = np.vectorize(predict_gear)(*params)

    gear[gear < MIN_GEAR] = MIN_GEAR

    gear = median_filter(times, gear, TIME_WINDOW)

    return clear_gear_fluctuations(times, gear, TIME_WINDOW)


def prediction_gears_gsm(
        correct_gear, gsm, velocities, accelerations, times=None,
        wheel_powers=None):
    """
    Predicts gears with a gear shifting matrix (cmv or gspv).

    :param correct_gear:
        A function to correct the gear predicted.
    :type correct_gear: function

    :param gsm:
        A gear shifting matrix (cmv or gspv).
    :type gsm: dict

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :param accelerations:
        Acceleration vector.
    :type accelerations: np.array

    :param times:
        Time vector.
        If None gears are predicted with cmv approach, otherwise with gspv.
    :type times: np.array, optional

    :param wheel_powers:
        Power at wheels vector.
        If None gears are predicted with cmv approach, otherwise with gspv.
    :type wheel_powers: np.array, optional

    :return:
        Predicted gears.
    :rtype: np.array
    """

    max_gear, min_gear = max(gsm), min(gsm)

    param = [min_gear, gsm[min_gear]]

    def predict_gear(velocity, acceleration, wheel_power=None):
        gear, (down, up) = param
        if wheel_power is not None:
            down, up = (down(wheel_power), up(wheel_power))
        if not down <= velocity < up:
            add = 1 if velocity >= up else -1
            while min_gear <= gear <= max_gear:
                gear += add
                if gear in gsm:
                    break
            gear = max(min_gear, min(max_gear, gear))

        g = correct_gear(velocity, acceleration, gear)

        if g in gsm:
            gear = g

        param[0], param[1] = (gear, gsm[gear])

        return max(MIN_GEAR, gear)

    predict = np.vectorize(predict_gear)

    args = [velocities, accelerations]
    if wheel_powers is not None:
        args.append(wheel_powers)

    gear = predict(*args)

    if times is not None:
        gear = median_filter(times, gear, TIME_WINDOW)
        gear = clear_gear_fluctuations(times, gear, TIME_WINDOW)

    return gear


def prediction_gears_gsm_hot_cold(
        correct_gear, gsm, time_cold_hot_transition, times, velocities,
        accelerations, wheel_powers=None):
    """
    Predicts gears with a gear shifting matrix (cmv or gspv) for cold and hot
    phases.

    :param correct_gear:
        A function to correct the gear predicted.
    :type correct_gear: function

    :param gsm:
        A gear shifting matrix (cmv or gspv).
    :type gsm: dict

    :param time_cold_hot_transition:
        Time at cold hot transition phase.
    :type time_cold_hot_transition: float

    :param times:
        Time vector.
    :type times: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :param accelerations:
        Acceleration vector.
    :type accelerations: np.array

    :param wheel_powers:
        Power at wheels vector.
        If None gears are predicted with cmv approach, otherwise with gspv.
    :type wheel_powers: np.array, optional

    :return:
        Predicted gears.
    :rtype: np.array
    """

    b = times <= time_cold_hot_transition

    gear = []

    for i in ['cold', 'hot']:
        args = [correct_gear, gsm[i], velocities[b], accelerations[b], times[b]]
        if wheel_powers is not None:
            args.append(wheel_powers[b])

        gear = np.append(gear, prediction_gears_gsm(*args))
        b = np.logical_not(b)

    return gear


def calculate_error_coefficients(
        engine_speeds, predicted_engine_speeds, velocities):
    """
    Calculates the prediction's error coefficients.

    :param engine_speeds:
        Engine speed vector.
    :type engine_speeds: np.array

    :param predicted_engine_speeds:
        Predicted engine speed vector.
    :type predicted_engine_speeds: np.array

    :param velocities:
        Velocity vector.
    :type velocities: np.array

    :return:
        - correlation coefficient.
        - mean absolute error.
    :rtype: dict
    """

    x = engine_speeds[velocities > VEL_EPS]
    y = predicted_engine_speeds[velocities > VEL_EPS]

    res = {
        'mean absolute error': mean_absolute_error(x, y),
        'correlation coeff.': np.corrcoef(x, y)[0, 1],
    }
    return res
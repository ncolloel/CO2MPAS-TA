#-*- coding: utf-8 -*-
#
# Copyright 2015 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

"""
It contains functions to predict the CO2 emissions.
"""


import numpy as np
from functools import partial
from scipy.integrate import trapz
from scipy.optimize import brute, minimize
from sklearn.metrics import mean_squared_error
from compas.dispatcher.utils import pairwise
from compas.functions.physical.constants import *
from inspect import isfunction


def calculate_normalized_engine_coolant_temperatures(
        engine_coolant_temperatures, temperature_target):
    """
    Calculates the normalized engine temperature [-].

    :param engine_coolant_temperatures:
        Engine coolant temperature vector [°C].
    :type engine_coolant_temperatures: np.array

    :param temperature_target:
        Normalization temperature [°C].
    :type temperature_target: float

    :return:
        Normalized engine temperature vector [-].
    :rtype: np.array
    """

    T = (engine_coolant_temperatures + 273.0) / (temperature_target + 273.0)

    T[T > 1] = 1.0

    return T


def calculate_brake_mean_effective_pressures(
        engine_speeds_out, engine_powers_out, engine_capacity):
    """
    Calculates engine brake mean effective pressure [bar].

    :param engine_speeds_out:
        Engine speed vector [RPM].
    :type engine_speeds_out: np.array, float

    :param engine_powers_out:
        Engine power vector [kW].
    :type engine_powers_out: np.array, float

    :param engine_capacity:
        Engine capacity [cm3].
    :type engine_capacity: float

    :return:
        Engine brake mean effective pressure vector [bar].
    :rtype: np.array, float
    """

    p = (1200000.0 / engine_capacity) * engine_powers_out / engine_speeds_out

    return np.nan_to_num(p)


def _calculate_fuel_mean_effective_pressure(
        params, n_speeds, n_powers, n_temperatures):

    p = params

    B = p['a'] + (p['b'] + p['c'] * n_speeds) * n_speeds
    C = np.power(n_temperatures, -p['t']) * (p['l'] + p['l2'] * n_speeds**2)
    C -= n_powers

    if p['a2'] == 0 and p['b2'] == 0:
        return -C / B, B

    A_2 = 2.0 * (p['a2'] + p['b2'] * n_speeds)

    v = np.sqrt(np.abs(B**2 - 2.0 * A_2 * C))

    return (-B + v) / A_2, v


def calculate_P0(params, engine_capacity, engine_stroke, idle_engine_speed,
                 engine_fuel_lower_heating_value):
    """
    Calculates the engine power threshold limit [kW].

    :param params:
        CO2 emission model parameters (a2, b2, a, b, c, l, l2, t, trg).

        The missing parameters are set equal to zero.
    :type params: dict

    :param engine_capacity:
        Engine capacity [cm3].
    :type engine_capacity: float

    :param engine_stroke:
        Engine stroke [mm].
    :type engine_stroke: float

    :param idle_engine_speed:
        Engine speed idle median and std [RPM].
    :type idle_engine_speed: (float, float)

    :param engine_fuel_lower_heating_value:
        Fuel lower heating value [kJ/kg].
    :type engine_fuel_lower_heating_value: float

    :return:
        Engine power threshold limit [kW].
    :rtype: float
    """

    p = {
        'a2': 0.0, 'b2': 0.0,
        'a': 0.0, 'b': 0.0, 'c': 0.0,
        'l': 0.0, 'l2': 0.0,
        't': 0.0, 'trg': 0.0
    }

    p.update(params)

    engine_cm_idle = idle_engine_speed[0] * engine_stroke / 30000.0

    lhv = engine_fuel_lower_heating_value
    FMEP = _calculate_fuel_mean_effective_pressure

    engine_wfb_idle, engine_wfa_idle = FMEP(p, engine_cm_idle, 0, 1)
    engine_wfa_idle = (3600000.0 / lhv) / engine_wfa_idle
    engine_wfb_idle *= (3.0 * engine_capacity / lhv * idle_engine_speed[0])

    return -engine_wfb_idle / engine_wfa_idle


def calculate_co2_emissions(
        engine_speeds_out, engine_powers_out, mean_piston_speeds,
        brake_mean_effective_pressures, engine_coolant_temperatures,
        engine_fuel_lower_heating_value, idle_engine_speed, engine_stroke,
        engine_capacity, engine_idle_fuel_consumption, fuel_carbon_content,
        params):
    """
    Calculates CO2 emissions [CO2g/s].

    :param engine_speeds_out:
        Engine speed vector [RPM].
    :type engine_speeds_out: np.array

    :param engine_powers_out:
        Engine power vector [kW].
    :type engine_powers_out: np.array

    :param mean_piston_speeds:
        Mean piston speed vector [m/s].
    :type mean_piston_speeds: np.array

    :param brake_mean_effective_pressures:
        Engine brake mean effective pressure vector [bar].
    :type brake_mean_effective_pressures: np.array

    :param engine_coolant_temperatures:
        Engine coolant temperature vector [°C].
    :type engine_coolant_temperatures: np.array

    :param engine_fuel_lower_heating_value:
        Fuel lower heating value [kJ/kg].
    :type engine_fuel_lower_heating_value: float

    :param idle_engine_speed:
        Engine speed idle median and std [RPM].
    :type idle_engine_speed: (float, float)

    :param engine_stroke:
        Engine stroke [mm].
    :type engine_stroke: float

    :param engine_capacity:
        Engine capacity [cm3].
    :type engine_capacity: float

    :param engine_idle_fuel_consumption:
        Fuel consumption at hot idle engine speed [g/s].
    :type engine_idle_fuel_consumption: float

    :param fuel_carbon_content:
        Fuel carbon content [CO2g/g].
    :type fuel_carbon_content: float

    :param params:
        CO2 emission model parameters (a2, b2, a, b, c, l, l2, t, trg).

        The missing parameters are set equal to zero.
    :type params: dict

    :return:
        CO2 emissions vector [CO2g/s].
    :rtype: np.array
    """

    # default params
    p = {
        'a2': 0.0, 'b2': 0.0,
        'a': 0.0, 'b': 0.0, 'c': 0.0,
        'l': 0.0, 'l2': 0.0,
        't': 0.0, 'trg': 0.0
    }

    # namespace shortcuts
    n_speeds = mean_piston_speeds
    n_powers = brake_mean_effective_pressures
    lhv = engine_fuel_lower_heating_value
    temp = calculate_normalized_engine_coolant_temperatures

    p.update(params)

    n_temperatures = temp(engine_coolant_temperatures, p['trg'])

    FMEP = partial(_calculate_fuel_mean_effective_pressure, p)

    fc = FMEP(n_speeds, n_powers, n_temperatures)[0]  # FMEP [bar]

    fc *= engine_speeds_out * (engine_capacity / (lhv * 1200))  # [g/sec]

    ec_P0 = calculate_P0(
        p, engine_capacity, engine_stroke, idle_engine_speed, lhv
    )

    #b = (engine_powers_out <= ec_P0)
    b = (engine_speeds_out < idle_engine_speed[0] + MIN_ENGINE_SPEED)
    # Idle fc correction for temperature
    idle_fc_temp_correction = n_temperatures**(-p['t'])
    fc[b] = engine_idle_fuel_consumption #* idle_fc_temp_correction[b]
    # fc[b] = engine_idle_fuel_consumption

    b = (engine_powers_out <= ec_P0) | (engine_speeds_out <= MIN_ENGINE_SPEED)
    #b = (engine_speeds_out <= ec_P0)
    fc[b | (fc < 0)] = 0

    co2 = fc * fuel_carbon_content

    return np.nan_to_num(co2)


def define_co2_emissions_model(
        engine_speeds_out, engine_powers_out, mean_piston_speeds,
        brake_mean_effective_pressures, engine_coolant_temperatures,
        engine_fuel_lower_heating_value, idle_engine_speed, engine_stroke,
        engine_capacity, engine_idle_fuel_consumption, fuel_carbon_content):
    """
    Returns CO2 emissions model (see :func:`calculate_co2_emissions`).

    :param engine_speeds_out:
        Engine speed vector [RPM].
    :type engine_speeds_out: np.array

    :param engine_powers_out:
        Engine power vector [kW].
    :type engine_powers_out: np.array

    :param mean_piston_speeds:
        Mean piston speed vector [m/s].
    :type mean_piston_speeds: np.array

    :param brake_mean_effective_pressures:
        Engine brake mean effective pressure vector [bar].
    :type brake_mean_effective_pressures: np.array

    :param engine_coolant_temperatures:
        Engine coolant temperature vector [°C].
    :type engine_coolant_temperatures: np.array

    :param engine_fuel_lower_heating_value:
        Fuel lower heating value [kJ/kg].
    :type engine_fuel_lower_heating_value: float

    :param idle_engine_speed:
        Engine speed idle median and std [RPM].
    :type idle_engine_speed: (float, float)

    :param engine_stroke:
        Engine stroke [mm].
    :type engine_stroke: float

    :param engine_capacity:
        Engine capacity [cm3].
    :type engine_capacity: float

    :param engine_idle_fuel_consumption:
        Fuel consumption at hot idle engine speed [g/s].
    :type engine_idle_fuel_consumption: float

    :param fuel_carbon_content:
        Fuel carbon content [CO2g/g].
    :type fuel_carbon_content: float

    :return:
        CO2 emissions model (co2_emissions = models(params)).
    :rtype: function
    """

    model = partial(
        calculate_co2_emissions, engine_speeds_out, engine_powers_out,
        mean_piston_speeds, brake_mean_effective_pressures,
        engine_coolant_temperatures, engine_fuel_lower_heating_value,
        idle_engine_speed, engine_stroke, engine_capacity,
        engine_idle_fuel_consumption, fuel_carbon_content
    )

    return model


def select_phases_integration_times(cycle_type):
    """
    Selects the cycle phases integration times [s].

    :param cycle_type:
        Cycle type (WLTP or NEDC).
    :type cycle_type: str

    :return:
        Cycle phases integration times [s].
    :rtype: tuple
    """

    _integration_times = {
        'WLTP': (0.0, 590.0, 1023.0, 1478.0, 1801.0),
        'NEDC': (0.0, 780.0, 1181.0)
    }

    return _integration_times[cycle_type.upper()]


def calculate_phases_distances(times, phases_integration_times, velocities):
    """
    Calculates cycle phases distances [km].

    :param times:
        Time vector [s].
    :type times: np.array

    :param phases_integration_times:
        Cycle phases integration times [s].
    :type phases_integration_times: tuple

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array

    :return:
        Cycle phases distances [km].
    :rtype: np.array
    """

    vel = velocities / 3600.0

    return calculate_cumulative_co2(times, phases_integration_times, vel)


def calculate_cumulative_co2(
        times, phases_integration_times, co2_emissions,
        phases_distances=1.0):
    """
    Calculates CO2 emission or cumulative CO2 of cycle phases [CO2g/km or CO2g].

    If phases_distances is not given the result is the cumulative CO2 of cycle
    phases [CO2g] otherwise it is CO2 emission of cycle phases [CO2g/km].

    :param times:
        Time vector [s].
    :type times: np.array

    :param phases_integration_times:
        Cycle phases integration times [s].
    :type phases_integration_times: tuple

    :param co2_emissions:
        CO2 instantaneous emissions vector [CO2g/s].
    :type co2_emissions: np.array

    :param phases_distances:
        Cycle phases distances [km].
    :type phases_distances: np.array, float, optional

    :return:
        CO2 emission or cumulative CO2 of cycle phases [CO2g/km or CO2g].
    :rtype: np.array
    """

    co2 = []

    for t0, t1 in pairwise(phases_integration_times):
        b = (t0 <= times) & (times < t1)
        co2.append(trapz(co2_emissions[b], times[b]))

    return np.array(co2) / phases_distances


def calculate_cumulative_co2_v1(phases_co2_emissions, phases_distances):
    """
    Calculates cumulative CO2 of cycle phases [CO2g].

    :param phases_co2_emissions:
        CO2 emission of cycle phases [CO2g/km].
    :type phases_co2_emissions: np.array

    :param phases_distances:
        Cycle phases distances [km].
    :type phases_distances: np.array

    :return:
        Cumulative CO2 of cycle phases [CO2g].
    :rtype: np.array
    """

    return phases_co2_emissions * phases_distances


def select_initial_co2_emission_model_params_guess(
        engine_type, engine_normalization_temperature,
        engine_normalization_temperature_window):
    """
    Selects initial guess and bounds of co2 emission model params.

    :param engine_type:
        Engine type (gasoline turbo, gasoline natural aspiration, diesel).
    :type engine_type: str

    :param engine_normalization_temperature:
        Engine normalization temperature [°C].
    :type engine_normalization_temperature: float

    :param engine_normalization_temperature_window:
        Engine normalization temperature limits [°C].
    :type engine_normalization_temperature_window: (float, float)

    :return:
        Initial guess and bounds of co2 emission model params.
    :rtype: (dict, dict)
    """

    p = {
        'x0': {
            't': 4.5,
            'trg': engine_normalization_temperature
        },
        'bounds': {
            't': (0.0, 8.0),
            'trg': engine_normalization_temperature_window
        }
    }

    params = {
        'gasoline turbo': {
            'x0': {
                'a': 0.468678, 'b': 0.011859,
                'c': -0.00069, 'a2': -0.00266,
                'l': -2.49882, 'l2': -0.0025
            },
            'bounds': {
                'a': (0.398589, 0.538767), 'b': (0.006558, 0.01716),
                'c': (-0.00099, -0.00038), 'a2': (-0.00354, -0.00179),
                'l': (-3.27698, -1.72066), 'l2': (-0.00796, 0.0)
            }
        },
        'gasoline natural aspiration': {
            'x0': {
                'a': 0.4719, 'b': 0.01193,
                'c': -0.00065, 'a2': -0.00385,
                'l': -2.14063, 'l2': -0.00286
            },
            'bounds': {
                'a': (0.40065, 0.54315), 'b': (-0.00247, 0.026333),
                'c': (-0.00138, 0.0000888), 'a2': (-0.00663, -0.00107),
                'l': (-3.17876, -1.1025), 'l2': (-0.00577, 0.0)
            }
        },
        'diesel': {
            'x0': {
                'a': 0.391197, 'b': 0.028604,
                'c': -0.00196, 'a2': -0.0012,
                'l': -1.55291, 'l2': -0.0076
            },
            'bounds': {
                'a': (0.346548, 0.435846), 'b': (0.002519, 0.054688),
                'c': (-0.00386, -0.000057), 'a2': (-0.00233, -0.000064),
                'l': (-2.2856, -0.82022), 'l2': (-0.01852, 0.0)
            }
        }
    }

    for k, v in params[engine_type].items():
        p[k].update(v)

    return p['x0'], p['bounds']


def identify_co2_emissions(
        co2_emissions_model, params_initial_guess, times,
        phases_integration_times, cumulative_co2_emissions):
    """
    Identifies instantaneous CO2 emission vector [CO2g/s].
    
    :param co2_emissions_model: 
        CO2 emissions model (co2_emissions = models(params)).
    :type co2_emissions_model: function
    
    :param params_initial_guess: 
        Initial guess of co2 emission model params.
    :type params_initial_guess: dict
    
    :param times:
        Time vector [s].
    :type times: np.array
    
    :param phases_integration_times:
        Cycle phases integration times [s].
    :type phases_integration_times: tuple
    
    :param cumulative_co2_emissions:
        Cumulative CO2 of cycle phases [CO2g].
    :type cumulative_co2_emissions: np.array

    :return:
        The instantaneous CO2 emission vector [CO2g/s].
    :rtype: np.array
    """

    co2_emissions = co2_emissions_model(params_initial_guess)

    it = zip(cumulative_co2_emissions, pairwise(phases_integration_times))
    for cco2, (t0, t1) in it:
        b = (t0 <= times) & (times < t1)
        co2_emissions[b] *= cco2 / trapz(co2_emissions[b], times[b])

    return co2_emissions


def define_co2_error_function(co2_emissions_model, co2_emissions):
    """
    Defines an error function to calibrate the CO2 emission model params.

    :param co2_emissions_model:
        CO2 emissions model (co2_emissions = models(params)).
    :type co2_emissions_model: function

    :param co2_emissions:
        CO2 instantaneous emissions vector [CO2g/s].
    :type co2_emissions: np.array

    :return:
        Error function to calibrate the CO2 emission model params.
    :rtype: function
    """

    def error_func(params):
        return mean_squared_error(co2_emissions, co2_emissions_model(params))

    return error_func


def define_co2_error_function_v1(
        co2_emissions_model, cumulative_co2_emissions, times,
        phases_integration_times):
    """
    Defines an error function to calibrate the CO2 emission model params.

    :param co2_emissions_model:
        CO2 emissions model (co2_emissions = models(params)).
    :type co2_emissions_model: function

    :param cumulative_co2_emissions:
        Cumulative CO2 of cycle phases [CO2g].
    :type cumulative_co2_emissions: np.array

    :param times:
        Time vector [s].
    :type times: np.array

    :param phases_integration_times:
        Cycle phases integration times [s].
    :type phases_integration_times: tuple

    :return:
        Error function to calibrate the CO2 emission model params.
    :rtype: function
    """

    def error_func(params):
        co2 = co2_emissions_model(params)
        cco2 = calculate_cumulative_co2(times, phases_integration_times, co2)
        return mean_squared_error(cumulative_co2_emissions, cco2)

    return error_func


def calibrate_model_params(params_bounds, error_function, initial_guess=None):
    """
    Calibrates the model params minimising the error_function.

    :param params_bounds:
        Bounds of model params.
    :type params_bounds: dict

    :param error_function:
        Model error function.
    :type error_function: function

    :param initial_guess:
        Initial guess of model params.

        If not specified a brute force is used to identify the best initial
        guess with in the bounds.
    :type initial_guess: dict, optional

    :return:
        Calibrated model params.
    :rtype: dict
    """

    if isfunction(error_function):
        error_f = error_function
    else:
        error_f = lambda p: sum(f(p) for f in error_function)

    param_keys, params_bounds = zip(*sorted(params_bounds.items()))

    params, min_e_and_p = {}, [np.inf, None]

    def update_params(params_values):
        params.update({k: v for k, v in zip(param_keys, params_values)})

    def error_func(params_values):
        update_params(params_values)

        res = error_f(params)

        if res < min_e_and_p[0]:
            min_e_and_p[0], min_e_and_p[1] = (res, params_values.copy())

        return res

    def finish(fun, x0, **kwargs):
        res = minimize(fun, x0, bounds=params_bounds)

        if res.success:
            return res.x, res.success

        return min_e_and_p[1], False

    if initial_guess is None:
        step = 3.0
        x = brute(error_func, params_bounds, Ns=step, finish=finish)
    else:
        x = finish(error_func, [initial_guess[k] for k in param_keys])[0]

    update_params(x)

    return params


def predict_co2_emissions(co2_emissions_model, params):
    """
    Predicts CO2 instantaneous emissions vector [CO2g/s].

    :param co2_emissions_model:
        CO2 emissions model (co2_emissions = models(params)).
    :type co2_emissions_model: function

    :param params:
        CO2 emission model parameters (a2, b2, a, b, c, l, l2, t, trg; e.g.
        {'a2':..., 'b2:..., ...}).

        The missing parameters are set equal to zero.
    :type params: dict

    :return:
        CO2 instantaneous emissions vector [CO2g/s].
    :rtype: np.array
    """

    return co2_emissions_model(params)


def calculate_fuel_consumptions(co2_emissions, fuel_carbon_content):
    """
    Calculates the instantaneous fuel consumption vector [g/s].

    :param co2_emissions:
        CO2 instantaneous emissions vector [CO2g/s].
    :type co2_emissions: np.array

    :param fuel_carbon_content:
        Fuel carbon content [CO2g/g].
    :type fuel_carbon_content: float

    :return:
        The instantaneous fuel consumption vector [g/s].
    :rtype: np.array
    """

    return co2_emissions / fuel_carbon_content


def calculate_co2_emission(phases_co2_emissions, phases_distances):
    """
    Calculates the CO2 emission of the cycle [CO2g/km].

    :param phases_co2_emissions:
        CO2 emission of cycle phases [CO2g/km].
    :type phases_co2_emissions: np.array

    :param phases_distances:
        Cycle phases distances [km].
    :type phases_distances: np.array, float

    :return:
        CO2 emission value of the cycle [CO2g/km].
    :rtype: float
    """

    n = sum(phases_co2_emissions * phases_distances)

    if isinstance(phases_distances, float):
        d = phases_distances * len(phases_co2_emissions)
    else:
        d = sum(phases_distances)

    return float(n / d)
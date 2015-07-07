__author__ = 'arcidvi'


import numpy as np
from math import cos, sin

def calculate_accelerations(times, velocities):
    """
    Calculates the acceleration from velocity time series.

    :param times:
        Time vector [s].
    :type times: np.array

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array

    :return:
        Acceleration vector [m/s2].
    :rtype: np.array
    """

    delta_time = np.diff(times)

    x = times[:-1] + delta_time / 2

    y = np.diff(velocities) / 3.6 / delta_time

    return np.interp(times, x, y)


def calculate_aerodynamic_resistances(f2, velocities):
    """
    Calculates the aerodynamic resistances of the vehicle.

    :param f2:
        As used in the dyno and defined by respective guidelines [N/(km/h)^2]
    :type f2: float

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array, float

    :return:
        Aerodynamic resistance vector [N].
    :rtype: np.array, float
    """

    return f2 * velocities**2


def calculate_aerodynamic_resistances_v1(air_density, Cd, A, velocities):
    """
    Calculates the aerodynamic resistances of the vehicle.

    :param air_density:
        Air density [kg/m3].
    :type air_density: float

    :param Cd:
        Aerodynamic drag coefficient [-].
    :type Cd: float

    :param A:
        Frontal area of the vehicle [m2].
    :type A: float

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array, float

    :return:
        Aerodynamic resistance vector [N].
    :rtype: np.array, float
    """

    return velocities**2 * (0.5 * Cd * A * air_density / 3.6**2)


def calculate_rolling_resistance(f0, angle_slope):
    """
    Calculates rolling resistance.

    :param f0:
        Rolling resistance force [N] when angle_slope == 0.
    :type f0: float

    :param angle_slope:
        Angle slope [rad].
    :type angle_slope: float

    :return:
        Rolling resistance force [N].
    :rtype: float
    """

    return f0 * cos(angle_slope)


def calculate_f0(vehicle_mass, rolling_resistance_coeff):
    """
    Calculates rolling resistance.

    :param vehicle_mass:
        Vehicle mass [kg].
    :type vehicle_mass: float

    :param rolling_resistance_coeff:
        Rolling resistance coefficient [-].
    :type rolling_resistance_coeff: float

    :return:
        Rolling resistance force [N] when angle_slope == 0.
    :rtype: float
    """

    return vehicle_mass * 9.81 * rolling_resistance_coeff


def calculate_velocity_resistances(f1, velocities):
    """
    Calculates forces function of velocity.

    :param f1:
        Defined by dyno procedure [N/(km/h)].
    :type f1: float

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array, float

    :return:
        Forces function of velocity.
    :rtype: np.array, float
    """

    return f1 * velocities


def calculate_climbing_force(vehicle_mass, angle_slope):
    """
    Calculates the vehicle climbing resistance.

    :param vehicle_mass:
        Vehicle mass [kg].
    :type vehicle_mass: float

    :param angle_slope:
        Angle slope [rad].
    :type angle_slope: float

    :return:
        Vehicle climbing resistance [N].
    :rtype: float
    """

    return vehicle_mass * 9.81 * sin(angle_slope)


def calculate_rotational_inertia_forces(
        vehicle_mass, inertial_factor, accelerations):
    """
    Calculate rotational inertia forces.

    :param vehicle_mass:
        Vehicle mass [kg].
    :type vehicle_mass: float

    :param inertial_factor:
        Factor that considers the rotational inertia [%].
    :type inertial_factor: float

    :param accelerations:
        Acceleration vector [m/s2].
    :type accelerations: np.array, float

    :return:
        Rotational inertia forces [N].
    :rtype: np.array, float
    """

    return vehicle_mass * inertial_factor * accelerations / 100


def select_inertial_factor(cycle_type):
    """
    Selects the inertia factor according to the cycle type (default is 3%).

    :param cycle_type:
        Cycle type (WLTP or NEDC).
    :type cycle_type: str

    :return:
        Factor that considers the rotational inertia [%].
    :rtype: float
    """

    _inertial_factor = {
        'WLTP': 3,
        'NEDC': 1.5
    }
    return _inertial_factor.get(cycle_type.upper(), 3)


def calculate_motive_forces(
        vehicle_mass, accelerations, climbing_force, aerodynamic_resistances,
        rolling_resistance, velocity_resistances, rotational_inertia_forces):
    """
    Calculate motive forces.

    :param vehicle_mass:
        Vehicle mass [kg].
    :type vehicle_mass: float

    :param accelerations:
        Acceleration vector [m/s2].
    :type accelerations: np.array, float

    :param climbing_force:
        Vehicle climbing resistance [N].
    :type climbing_force: float

    :param rolling_resistance:
        Rolling resistance force [N].
    :type rolling_resistance: float

    :param aerodynamic_resistances:
        Aerodynamic resistance vector [N].
    :type aerodynamic_resistances: np.array, float

    :param velocity_resistances:
        Forces function of velocity.
    :type velocity_resistances: np.array, float

    :param rotational_inertia_forces:
        Rotational inertia forces [N].
    :type rotational_inertia_forces: np.array, float

    :return:
        Motive forces [N].
    :rtype: np.array, float
    """

    # namespace shortcuts
    Frr = rolling_resistance
    Faero = aerodynamic_resistances
    Fclimb = climbing_force
    Fvel = velocity_resistances
    Finertia = rotational_inertia_forces

    return vehicle_mass * accelerations + Fclimb + Frr + Faero + Fvel + Finertia


def calculate_motive_powers(motive_forces, velocities):
    """
    Calculates motive power.

    :param motive_forces:
        Motive forces [N].
    :type motive_forces: np.array, float

    :param velocities:
        Velocity vector [km/h].
    :type velocities: np.array, float

    :return:
        Motive power [kW].
    :rtype: np.array, float
    """

    return motive_forces * velocities / 3600
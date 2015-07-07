__author__ = 'arcidvi'
from math import pi


def evaluate_gear_box_torque_in(
        gear_box_torque_out, gear_box_speed_in, gear_box_speed_out,
        gear_box_efficiency_parameters):
    """
    Calculates torque required according to the temperature profile.

    :param gear_box_torque_out:
        Torque gear_box.
    :type gear_box_torque_out: float

    :param gear_box_speed_in:
        Engine speed.
    :type gear_box_speed_in: float

    :param gear_box_speed_out:
        Wheel speed.
    :type gear_box_speed_out: float

    :param par:
        Parameters of gear box efficiency model:

            - `gbp00`,
            - `gbp10`,
            - `gbp01`
    :type par: dict

    :return:
        Torque required.
    :rtype: float
    """

    tgb, es, ws = gear_box_torque_out, gear_box_speed_in, gear_box_speed_out
    par = gear_box_efficiency_parameters
    if tgb < 0:
        return par['gbp01'] * tgb - par['gbp10'] * ws - par['gbp00']
    elif es > 0 and ws > 0:
        return (tgb - par['gbp10'] * es - par['gbp00']) / par['gbp01']
    return 0


def calculate_gear_box_torque_in(
        gear_box_torque_out, gear_box_speed_in, gear_box_speed_out,
        gear_box_temperature, gear_box_efficiency_parameters_cold_hot,
        temperature_references):
    """
    Calculates torque required according to the temperature profile.

    :param gear_box_torque_out:
        Torque gear box.
    :type gear_box_torque_out: float

    :param gear_box_speed_in:
        Engine speed.
    :type gear_box_speed_in: float

    :param gear_box_speed_out:
        Wheel speed.
    :type gear_box_speed_out: float

    :param gear_box_temperature:
        Temperature.
    :type gear_box_temperature: float

    :param gear_box_efficiency_parameters_cold_hot:
        Parameters of gear box efficiency model for cold/hot phases:

            - 'hot': `gbp00`, `gbp10`, `gbp01`
            - 'cold': `gbp00`, `gbp10`, `gbp01`
    :type gear_box_efficiency_parameters_cold_hot: dict

    :param temperature_references:
        Cold and hot reference temperatures.
    :type temperature_references: tuple

    :return:
        Torque required according to the temperature profile.
    :rtype: float
    """

    par = gear_box_efficiency_parameters_cold_hot
    T_cold, T_hot = temperature_references
    t_out, e_s, gb_s = gear_box_torque_out, gear_box_speed_in, gear_box_speed_out

    t = evaluate_gear_box_torque_in(t_out, e_s, gb_s, par['hot'])

    if not T_cold == T_hot and gear_box_temperature <= T_hot:

        t_cold = evaluate_gear_box_torque_in(t_out, e_s, gb_s, par['cold'])

        t += (T_hot - gear_box_temperature) / (T_hot - T_cold) * (t_cold - t)

    return t


def correct_gear_box_torque_in(
        gear_box_torque_out, gear_box_torque_in, gear, gear_box_ratios):
    """
    Corrects the torque when the gear box ratio is equal to 1.

    :param gear_box_torque_out:
        Torque gear_box.
    :type gear_box_torque_out: float

    :param gear_box_torque_in:
        Torque required.
    :type gear_box_torque_in: float

    :param gear:
        Gear.
    :type gear: int

    :return:
        Corrected torque required.
    :rtype: float
    """

    gbr = gear_box_ratios

    return gear_box_torque_out if gbr.get(gear, 0) == 1 else gear_box_torque_in


def calculate_gear_box_efficiency(
        gear_box_power_out, gear_box_speed_in, gear_box_speed_out,
        gear_box_torque_out, gear_box_torque_in):
    """
    Calculates torque entering the gear box.

    :param gear_box_power_out:
        Power at wheels.
    :type gear_box_power_out: float

    :param gear_box_speed_in:
        Engine speed.
    :type gear_box_speed_in: float

    :param gear_box_speed_out:
        Wheel speed.
    :type gear_box_speed_out: float

    :return:

        - Gear box efficiency.
        - Torque loss.
    :rtype: (float, float)

    .. note:: Torque entering the gearbox can be from engine side
       (power mode or from wheels in motoring mode).
    """

    eff, torque_loss = 0, gear_box_torque_in - gear_box_torque_out
    if gear_box_torque_in == gear_box_torque_out:
        eff = 1
    else:
        eff = gear_box_torque_in / gear_box_power_out * (pi / 30000)
        eff = 1 / (gear_box_speed_in * eff) if gear_box_power_out > 0 else gear_box_speed_out * eff

    return max(0, min(1, eff)), torque_loss


def calculate_gear_box_temperature(
        gear_box_heat, starting_temperature, equivalent_gear_box_heat_capacity,
        thermostat_temperature):
    """
    Calculates the gear box temperature not finalized [°].

    :param gear_box_heat:
        Gear box heat.
    :type gear_box_heat: float

    :param starting_temperature:
        Starting temperature.
    :type starting_temperature: float

    :param equivalent_gear_box_heat_capacity:
        Equivalent gear box capacity (from cold start model).
    :type equivalent_gear_box_heat_capacity: float

    :param thermostat_temperature:
        Thermostat temperature [°].
    :type thermostat_temperature: float

    :return:
        Gear box temperature not finalized.
    :rtype: float
    """

    temp = starting_temperature + gear_box_heat / equivalent_gear_box_heat_capacity

    return min(temp, thermostat_temperature - 5.0)


def calculate_gear_box_heat(gear_box_efficiency, gear_box_power_out):
    """
    Calculates the gear box temperature heat.

    :param gear_box_efficiency:
        Gear box efficiency.
    :type gear_box_efficiency: float

    :param gear_box_power_out:
        Power at wheels.
    :type gear_box_power_out: float

    :return:
        Gear box heat.
    :rtype: float
    """

    if gear_box_efficiency and gear_box_power_out:
        return abs(gear_box_power_out) * (1.0 - gear_box_efficiency) * 1000.0

    return 0
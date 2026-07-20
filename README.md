2030 autumn Station Control — Power-Flow Results

This directory contains the PowerFactory AC power-flow results for the 2030 autumn operating case (autumn462). The case uses Station Controllers to coordinate reactive-power control among generators connected to the same bus. Distributed Slack diagnostics and German cross-border transmission statistics are also included.

## Files

### `bus_results.csv`

Voltage, angle, and geographical data for 60 buses.

- `name`: Bus name.
- `uknom_kv`: Nominal bus voltage in kV.
- `u_pu`: Calculated bus voltage in per unit.
- `u_kv`: Calculated bus voltage in kV.
- `angle_deg`: Voltage angle in degrees.
- `outserv`: Service status; 0 means in service.
- `longitude`, `latitude`: Bus geographical coordinates.

### `line_results.csv`

Power flows, capacities, currents, and loading results for all 130 AC transmission lines.

- `from_bus`, `to_bus`: Buses at both ends of the line.
- `rated_mva_from_current`: Line capacity calculated from nominal voltage and rated current, in MVA.
- `apparent_from_mva`, `apparent_to_mva`: Apparent power at both line ends, in MVA.
- `loading_calc_percent`: Capacity utilisation calculated using the larger apparent-power value at either end.
- `p_from_mw`, `p_to_mw`: Active power at both ends, in MW.
- `q_from_mvar`, `q_to_mvar`: Reactive power at both ends, in Mvar.
- `i_from_ka`, `i_to_ka`: Current at both ends, in kA.
- `loading_percent`: Line loading reported by PowerFactory.
- `outserv`: Service status.

### `generator_results.csv`

Setpoints, reactive-power limits, control settings, and calculated results for all 597 `ElmGenstat` objects. These include conventional generators, renewable generators, HVDC active-power equivalents, and HVDC qcap devices.

- `bus`: Generator connection bus.
- `pgini_mw`, `qgini_mvar`: Active- and reactive-power setpoints before the power flow.
- `sgn_mva`: Rated apparent power.
- `q_min_mvar_pf`, `q_max_mvar_pf`: Reactive-power limits written to PowerFactory.
- `control_attr`, `control_value`: Generator control attribute and value.
- `usetp_pu`: Voltage setpoint.
- `p_result_mw`, `q_result_mvar`: Calculated active and reactive power.
- `desc`: Import and control information stored in the object description.

For the Station Control case, use `q_result_mvar` together with `bus` to examine how reactive power is shared among generators connected to the same bus.

### `load_results.csv`

Setpoints and calculated results for 72 load objects, including ordinary loads and HVDC receiving-end equivalent loads.

- `plini_mw`, `qlini_mvar`: Initial active- and reactive-power setpoints.
- `p_result_mw`, `q_result_mvar`: Calculated load powers.
- `outserv`: Service status.

The setpoints and calculated powers may differ when voltage-dependent load behaviour is enabled.

### `slack_results.csv`

Results for the two External Grid / Slack objects.

- `bus`: Slack connection bus.
- `usetp_pu`: Voltage setpoint.
- `p_mw`, `q_mvar`: Active and reactive power supplied or absorbed by the External Grid.
- `outserv`: Service status.

### `distributed_slack_results.csv`

Distributed Slack diagnostics for 582 ordinary generators. Pure reactive-power `hvdc_qcap_*` devices are excluded from this active-power allocation analysis.

- `p_schedule_mw`: Scheduled active power before the power flow.
- `p_result_mw`: Calculated active power.
- `delta_p_mw`: Difference between calculated and scheduled active power.
- `participates_observed`: 1 if an active-power adjustment above the diagnostic tolerance was observed.
- `observed_share`: Share of the total observed active-power adjustment.
- `result_sign_reversed`: Indicates whether the script reversed the raw PowerFactory port-power sign.

### `germany_neighbor_line_capacity_detail.csv`

Detailed results for 19 AC interconnectors between Germany and neighbouring countries.

- `neighbor_country_code`, `neighbor_country`: Neighbouring-country code and name.
- `germany_bus`, `neighbor_bus`: German-side and neighbouring-side buses.
- `rated_capacity_mva`: Rated line capacity.
- `used_apparent_power_mva`: Larger apparent-power value at either end of the line.
- `capacity_utilization_percent`: Line capacity utilisation.
- `net_export_from_germany_mw`: German-side active power; positive means German export and negative means German import.
- `flow_direction`: Text description of the active-power direction.
- `line_capacity_share_within_border_percent`: The line's share of the total capacity on the corresponding German border.
- `line_capacity_share_all_germany_borders_percent`: The line's share of Germany's total AC interconnector capacity in this model.

### `germany_neighbor_line_capacity_summary.csv`

German interconnector results aggregated by neighbouring country, covering seven country borders.

- `line_count`: Number of AC interconnectors on the border.
- `total_rated_capacity_mva`: Total rated capacity on the border.
- `total_used_apparent_power_mva`: Sum of used apparent power across the border lines.
- `capacity_weighted_utilization_percent`: Capacity-weighted border utilisation.
- `maximum_line_utilization_percent`: Highest individual line utilisation on the border.
- `net_export_from_germany_mw`: German net export to the neighbouring country; a negative value means net import.
- `net_flow_direction`: Net active-power direction.
- `border_capacity_share_all_germany_borders_percent`: The border's share of Germany's total AC interconnector capacity in this model.

## Units and Sign Conventions

- Active power: MW.
- Reactive power: Mvar.
- Apparent power and capacity: MVA.
- Voltage: kV or pu.
- Current: kA.
- Loading and capacity shares: percent.
- PowerFactory element-terminal powers follow its terminal sign convention. Cross-border results have been normalised so that German net export is positive and German net import is negative.

## Suggested Use

- Use `bus_results.csv` to analyse voltage levels and voltage angles.
- Use `line_results.csv` to identify line loading and overloads.
- Use `generator_results.csv`, grouped by `bus`, to analyse Station Controller reactive-power sharing.
- Use `distributed_slack_results.csv` to analyse active-power balancing.
- Use the two `germany_neighbor_line_capacity_*.csv` files for German cross-border capacity and exchange analysis.

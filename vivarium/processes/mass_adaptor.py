from vivarium.core.process import Deriver
from vivarium.library.units import units


class MassToConcentration(Deriver):
    """ Adapts mass variable to mass concentration """

    defaults = {
        'input_mass_units': 1.0 * units.fg,
        'input_volume_units': 1.0 * units.fL,
        'output_concentration_units': 1.0 * units.mmolar,
        'characteristic_output_volume': 1.0 * units.fL,
        'mass_species_molecular_weight': 1.0 * units.fg / units.molec
    }

    def initial_state(self, config=None):
        return {}

    def ports_schema(self):
        return {
            'input': {
                'mass': {
                    '_default': 1.0 * self.parameters['input_mass_units'],
                },
                'volume': {
                    '_default': 1.0 * self.parameters['input_volume_units']}
            },
            'output': {
                'biomass': {
                    '_default': 1.0,
                    '_update': 'set',
                }
            }
        }

    def next_update(self, timestep, states):
        mass = states['input']['mass']

        # do conversion
        # Concentration = mass/molecular_weight/characteristic volume
        # Note: Biomass is also used to set Volume, so here we just set the scale
        mass_species_conc = mass / self.config['mass_species_molecular_weight'] / (
            self.config['characteristic_output_volume'])

        update = {
            'output': {
                # Return the correct units, with units stripped away
                'biomass': mass_species_conc.to(self.config['output_concentration_units']).magnitude
            }
        }
        return update


class MassToCount(Deriver):
    """ Adapts mass variable to mass concentration """

    defaults = {
        'input_mass_units': 1.0 * units.fg,
        'mass_species_molecular_weight': 1.0 * units.fg / units.molec
    }

    def initial_state(self, config=None):
        return {}

    def ports_schema(self):
        return {
            'input': {
                'mass': {
                    '_default': 1.0 * units.fg,
                },
            },
            'output': {
                'biomass': {
                    '_default': 1.0,
                    '_update': 'set',
                }
            }
        }

    def next_update(self, timestep, states):
        mass = states['input']['mass']

        # do conversion
        # count = mass/molecular_weight
        # Note: Biomass is also used to set Volume, so here we just set the scale
        mass_species_count = mass / self.config['mass_species_molecular_weight']

        update = {
            'output': {
                # Return the correct units, with units stripped away
                'biomass': mass_species_count.magnitude
            }
        }
        return update

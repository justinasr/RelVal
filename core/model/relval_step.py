"""
Module that contains RelValStep class
"""
import weakref
import json
from copy import deepcopy
from core.model.model_base import ModelBase


class RelValStep(ModelBase):

    _ModelBase__schema = {
        # PrepID
        'name': '',
        # Arguments if step is a cmsDriver step
        'arguments': {
            "beamspot": "",
            "conditions": "",
            "customise": "",
            "data": False,
            "datatier": [],
            "era": "",
            "eventcontent": [],
            "fast": False,
            "filetype": "",
            "hltProcess": "",
            "mc": False,
            "no_exec": False,
            "number": 1,
            "pileup": "",
            "pileup_input": "",
            "process": "",
            "relval": "",
            "runUnscheduled": False,
            "scenario": "",
            "step": [],
        },
        # Hash of configuration file uploaded to ReqMgr2
        'config_id': '',
        # Input information if step is list of input files
        'input': {
            "dataset": "",
            "lumisections": {},
            "label": "",
            "events": 0,
        },
    }

    lambda_checks = {
        'config_id': lambda cid: ModelBase.matches_regex(cid, '[a-f0-9]{0,50}'),
    }

    def __init__(self, json_input=None, parent=None):
        self.parent = None
        if json_input:
            json_input = deepcopy(json_input)
            # Remove -- from argument names
            if json_input.get('input', {}).get('dataset'):
                # Input step
                json_input['arguments'] = {}
            else:
                # cmsDriver step
                json_input['arguments'] = {k.lstrip('-'): v for k, v in json_input['arguments'].items()}
                json_input['input'] = {}

        ModelBase.__init__(self, json_input)
        if parent:
            self.parent = weakref.ref(parent)

    def get_index_in_parent(self):
        """
        Return step's index in parent's list of steps
        """
        for index, step in enumerate(self.parent().get('steps')):
            if self == step:
                return index

        raise Exception(f'Sequence is not a child of {self.parent().get_prepid()}')

    def get_step_type(self):
        """
        Return whether this is cmsDriver or input file step
        """
        if self.get('input').get('dataset'):
            return 'input_file'

        return 'cmsDriver'

    def __build_cmsdriver(self, step_index, arguments):
        """
        Build a cmsDriver command from given arguments
        Add comment in front of the command
        """
        # cfg attribyte might have step name
        cmsdriver_type = arguments.get('cfg', f'step{step_index}')
        self.logger.info('Generating %s cmsDriver for step %s', cmsdriver_type, step_index)
        # Actual command
        command = f'# Command for step {step_index + 1}:\ncmsDriver.py {cmsdriver_type}'
        # Comment in front of the command for better readability
        comment = f'# Arguments for step {step_index + 1}:\n'
        for key in sorted(arguments.keys()):
            if not arguments[key]:
                continue

            if key in ('extra', 'cfg'):
                continue

            if isinstance(arguments[key], bool):
                arguments[key] = ''

            if isinstance(arguments[key], list):
                arguments[key] = ','.join([str(x) for x in arguments[key]])

            command += f' --{key} {arguments[key]}'.rstrip()
            comment += f'# --{key} {arguments[key]}'.rstrip() + '\n'

        if arguments.get('extra'):
            extra_value = arguments['extra']
            command += f' {extra_value}'
            comment += f'# <extra> {extra_value}\n'

        # Exit the script with error of cmsDriver.py
        command += ' || exit $?'

        return comment + '\n' + command

    def __build_das_command(self, step_index, input_info):
        """
        Build a dasgoclient command to fetch input dataset file names
        """
        dataset = input_info['dataset']
        runs = input_info['lumisection']
        if not runs:
            return f'# Step {step_index + 1} is input dataset for next step: {dataset}'

        files_name = f'step{step_index + 1}_files.txt'
        lumis_name = f'step{step_index + 1}_lumi_ranges.txt'
        comment = f'# Arguments for step {step_index + 1}:\n'
        command = f'# Command for step {step_index + 1}:\n'
        comment += f'#   dataset: {dataset}\n'
        command += f'echo "" > {files_name}\n'
        for run, run_info in runs.items():
            for lumi_range in run_info:
                comment += f'#   run: {run}, range: {lumi_range[0]} - {lumi_range[1]}\n'
                command += f'dasgoclient --limit 0 --format json '
                command += f'--query "lumi,file dataset={dataset} run={run}"'
                command += f' | das-selected-lumis.py {lumi_range[0]},{lumi_range[1]}'
                command += f' | sort -u >> {files_name}\n'

        lumi_json = json.dumps(runs)
        command += f'echo \'{lumi_json}\' > {lumis_name}'
        return comment + '\n' + command

    def get_command(self):
        """
        Return a cmsDriver command for this step
        Config file is named like this
        """
        input_dict = self.get('input')
        step_type = self.get_step_type()
        index = self.get_index_in_parent()
        if index == 0 and step_type == 'input_file':
            return self.__build_das_command(index, input_dict)

        arguments_dict = dict(self.get('arguments'))
        # Delete sequence metadata
        if 'config_id' in arguments_dict:
            del arguments_dict['config_id']

        # Handle input/output file names
        name = self.get('name')
        all_steps = self.parent().get('steps')
        arguments_dict['fileout'] = f'"file:step{index + 1}.root"'
        arguments_dict['python_filename'] = f'{name}.py'
        arguments_dict['no_exec'] = True

        skip_eventcontent = {'DQM'}
        if index != 0:
            previous = all_steps[index - 1]
            previous_type = previous.get_step_type()
            if previous_type == 'input_file':
                previous_input = previous.get('input')
                if previous_input['lumisection']:
                    # If there are lumi ranges, add a file with them and list of files as input
                    arguments_dict['filein'] = f'"filelist:step{index}_files.txt"'
                    arguments_dict['lumiToProcess'] = f'"step{index}_lumi_ranges.txt"'
                else:
                    # If there are no lumi ranges, use input file normally
                    previous_dataset = previous_input['dataset']
                    arguments_dict['filein'] = f'"dbs:{previous_dataset}"'
            else:
                previous_arguments = previous.get('arguments')
                previous_eventcontent = previous_arguments.get('eventcontent', [])
                previous_eventcontent = [x for x in previous_eventcontent if x not in skip_eventcontent]
                if self.__has_step('HARVESTING', arguments_dict['step']):
                    arguments_dict['filein'] = f'"file:{self.__dqm_step_output(all_steps)}"'
                else:
                    arguments_dict['filein'] = f'"file:step{index}.root"'

        cms_driver_command = self.__build_cmsdriver(index, arguments_dict)
        return cms_driver_command

    def __has_step(self, step, list_of_steps):
        if isinstance(list_of_steps, str):
            self.logger.warning('Conversting str steps to a list')
            list_of_steps = list_of_steps.split(',')

        for one_step in list_of_steps:
            if one_step.startswith(step):
                return True

        return False

    def __dqm_step_output(self, all_steps):
        for step_index, step in enumerate(all_steps):
            if self.__has_step('DQM', step.get('arguments').get('step', [])):
                return f'step{step_index + 1}_inDQM.root'

        raise Exception('No DQM step could be found')
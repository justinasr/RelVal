"""
Module that contains Ticket class
"""
from copy import deepcopy
from core.model.model_base import ModelBase


class Ticket(ModelBase):
    """
    Ticket allows to create multiple similar RelVals in the same campaign
    """

    _ModelBase__schema = {
        # Database id (required by database)
        '_id': '',
        # PrepID
        'prepid': '',
        # Batch name
        'batch_name': '',
        # CMSSW release
        'cmssw_release': '',
        # Additional command to add to all cmsDrivers
        'command': '',
        # CPU cores
        'cpu_cores': 1,
        # List of prepids of relvals that were created from this ticket
        'created_relvals': [],
        # Action history
        'history': [],
        # Label to be used in runTheMatrix
        'label': '',
        # Type of relval: standard, upgrade, premix, etc.
        'matrix': 'standard',
        # Memory in MB
        'memory': 2000,
        # User notes
        'notes': '',
        # Whether to recycle first step
        'recycle_gs': False,
        # String to rewrite middle part of INPUT dataset(s) /.../THIS/...
        'rewrite_gt_string': '',
        # Tag to group workflow ids
        'sample_tag': '',
        # Status is either new or done
        'status': 'new',
        # Workflow ids
        'workflow_ids': [],
    }

    lambda_checks = {
        'prepid': lambda prepid: ModelBase.matches_regex(prepid, '[a-zA-Z0-9_\\-]{1,75}'),
        'batch_name': ModelBase.lambda_check('batch_name'),
        'cmssw_release': ModelBase.lambda_check('cmssw_release'),
        'cpu_cores': ModelBase.lambda_check('cpu_cores'),
        '__created_relvals': ModelBase.lambda_check('relval'),
        'label': ModelBase.lambda_check('label'),
        'matrix': ModelBase.lambda_check('matrix'),
        'memory': ModelBase.lambda_check('memory'),
        'rewrite_gt_string': lambda rgs: ModelBase.matches_regex(rgs, '[a-zA-Z0-9\\.\\-_]{0,199}'),
        'sample_tag': ModelBase.lambda_check('sample_tag'),
        'status': lambda status: status in ('new', 'done'),
        'workflow_ids': lambda wf: len(wf) > 0,
        '__workflow_ids': lambda wf: wf > 0,

    }

    def __init__(self, json_input=None, check_attributes=True):
        if json_input:
            json_input = deepcopy(json_input)
            json_input['workflow_ids'] = [float(wid) for wid in json_input['workflow_ids']]
            json_input['recycle_gs'] = bool(json_input.get('recycle_gs', False))

        ModelBase.__init__(self, json_input, check_attributes)

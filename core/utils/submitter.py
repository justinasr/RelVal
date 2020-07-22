"""
Module that has all classes used for request submission to computing
"""
import json
import os
import time
from core_lib.utils.ssh_executor import SSHExecutor
from core_lib.utils.locker import Locker
from core_lib.database.database import Database
from core_lib.utils.settings import Settings
from core_lib.utils.connection_wrapper import ConnectionWrapper
from core_lib.utils.submitter import Submitter as BaseSubmitter
from core_lib.utils.common_utils import clean_split
from core.utils.emailer import Emailer


class RequestSubmitter(BaseSubmitter):

    def add(self, relval, relval_controller):
        prepid = relval.get_prepid()
        super().add_task(prepid,
                         self.submit_relval,
                         relval=relval,
                         controller=relval_controller)

    def __handle_error(self, relval, error_message):
        """
        Handle error that occured during submission, modify RelVal accordingly
        """
        self.logger.error(error_message)
        relval_db = Database('relvals')
        relval.set('status', 'new')
        relval.add_history('submission', 'failed', 'automatic')
        for step in relval.get('steps'):
            step.set('config_id', '')

        relval_db.save(relval.get_json())
        service_url = Settings().get('service_url')
        emailer = Emailer()
        prepid = relval.get_prepid()
        subject = f'RelVal {prepid} submission failed'
        body = f'Hello,\n\nUnfortunately submission of {prepid} failed.\n'
        body += (f'You can find this relval at '
                 f'{service_url}/relval/relvals?prepid={prepid}\n')
        body += f'Error message:\n\n{error_message}'
        recipients = emailer.get_recipients(relval)
        emailer.send(subject, body, recipients)

    def __handle_success(self, relval):
        """
        Handle notification of successful submission
        """
        prepid = relval.get_prepid()
        last_workflow = relval.get('workflows')[-1]['name']
        cmsweb_url = Settings().get('cmsweb_url')
        self.logger.info('Submission of %s succeeded', prepid)
        service_url = Settings().get('service_url')
        emailer = Emailer()
        subject = f'RelVal {prepid} submission succeeded'
        body = f'Hello,\n\nSubmission of {prepid} succeeded.\n'
        body += (f'You can find this relval at '
                 f'{service_url}/relval/relvals?prepid={prepid}\n')
        body += f'Workflow in ReqMgr2 {cmsweb_url}/reqmgr2/fetch?rid={last_workflow}'
        recipients = emailer.get_recipients(relval)
        emailer.send(subject, body, recipients)

    def __prepare_workspace(self, relval, controller, ssh_executor):
        """
        Clean or create a remote directory and upload all needed files
        """
        prepid = relval.get_prepid()
        ssh_executor.execute_command([f'rm -rf relval_submission/{prepid}',
                                      f'mkdir -p relval_submission/{prepid}'])
        with open(f'/tmp/{prepid}_generate.sh', 'w') as temp_file:
            config_file_content = controller.get_cmsdriver(relval, for_submission=True)
            temp_file.write(config_file_content)

        with open(f'/tmp/{prepid}_upload.sh', 'w') as temp_file:
            upload_file_content = controller.get_config_upload_file(relval)
            temp_file.write(upload_file_content)

        # Upload config generation script - cmsDrivers
        ssh_executor.upload_file(f'/tmp/{prepid}_generate.sh',
                                 f'relval_submission/{prepid}/config_generate.sh')
        # Upload config upload to ReqMgr2 script
        ssh_executor.upload_file(f'/tmp/{prepid}_upload.sh',
                                 f'relval_submission/{prepid}/config_upload.sh')
        # Upload python script used by upload script
        ssh_executor.upload_file('./core_lib/utils/config_uploader.py',
                                 f'relval_submission/{prepid}/config_uploader.py')

        os.remove(f'/tmp/{prepid}_generate.sh')
        os.remove(f'/tmp/{prepid}_upload.sh')

    def __check_for_submission(self, relval):
        """
        Perform one last check of values before submitting a RelVal
        """
        if relval.get('status') != 'submitting':
            raise Exception(f'Cannot submit a request with status {relval.get("status")}')

    def __generate_configs(self, relval, ssh_executor):
        """
        SSH to a remote machine and generate cmsDriver config files
        """
        prepid = relval.get_prepid()
        command = [f'cd relval_submission/{prepid}',
                   'chmod +x config_generate.sh',
                   'voms-proxy-init -voms cms --valid 4:00 --out $(pwd)/proxy.txt',
                   'export X509_USER_PROXY=$(pwd)/proxy.txt',
                   './config_generate.sh']
        stdout, stderr, exit_code = ssh_executor.execute_command(command)
        if exit_code != 0:
            self.__handle_error(relval, f'Error generating configs for {prepid}.\n{stderr}')
            return None

        return stdout

    def __upload_configs(self, relval, ssh_executor):
        """
        SSH to a remote machine and upload cmsDriver config files to ReqMgr2
        """
        prepid = relval.get_prepid()
        command = [f'cd relval_submission/{prepid}',
                   'chmod +x config_upload.sh',
                   'export X509_USER_PROXY=$(pwd)/proxy.txt',
                   './config_upload.sh']
        stdout, stderr, exit_code = ssh_executor.execute_command(command)
        if exit_code != 0:
            self.__handle_error(relval, f'Error uploading configs for {prepid}.\n{stderr}')
            return None

        stdout = [x for x in clean_split(stdout, '\n') if 'DocID' in x]
        # Get all lines that have DocID as tuples split by space
        stdout = [tuple(clean_split(x.strip(), ' ')[1:]) for x in stdout]
        return stdout

    def submit_relval(self, relval, controller):
        """
        Method that is used by submission workers. This is where the actual submission happens
        """
        credentials_path = Settings().get('credentials_path')
        ssh_executor = SSHExecutor('lxplus.cern.ch', credentials_path)
        prepid = relval.get_prepid()
        self.logger.debug('Will try to acquire lock for %s', prepid)
        with Locker().get_lock(prepid):
            self.logger.info('Locked %s for submission', prepid)
            relval_db = Database('relvals')
            relval = controller.get(prepid)
            self.__check_for_submission(relval)
            self.__prepare_workspace(relval, controller, ssh_executor)
            # Start executing commands
            # Create configs
            self.__generate_configs(relval, ssh_executor)
            # Upload configs
            config_hashes = self.__upload_configs(relval, ssh_executor)
            self.logger.debug(config_hashes)
            # Iterate through uploaded configs and save their hashes in RelVal steps
            for step in relval.get('steps'):
                step_config_name = step.get_config_file_name()
                if not step_config_name:
                    continue

                for config_pair in config_hashes:
                    config_name, config_hash = config_pair
                    if step_config_name == config_name:
                        step.set('config_id', config_hash)
                        config_hashes.remove(config_pair)
                        break
                else:
                    step_name = step.get('name')
                    self.__handle_error(relval, f'Could not find hash for {step_name}')
                    return

            if config_hashes:
                self.__handle_error(relval, f'Unused hashes: {config_hashes}')
                return

            for step in relval.get('steps'):
                step_config_name = step.get_config_file_name()
                if not step_config_name:
                    continue

                if not step.get('config_id'):
                    step_name = step.get('name')
                    self.__handle_error(relval, f'Missing hash for step {step_name}')
                    return

            try:
                job_dict = controller.get_job_dict(relval)
            except Exception as ex:
                self.__handle_error(relval, f'Error getting {prepid} job dict:\n{str(ex)}')
                return

            headers = {'Content-type': 'application/json',
                       'Accept': 'application/json'}

            cmsweb_url = Settings().get('cmsweb_url')
            connection = ConnectionWrapper(host=cmsweb_url, keep_open=True)
            try:
                # Submit job dictionary (ReqMgr2 JSON)
                reqmgr_response = connection.api('POST',
                                                 '/reqmgr2/data/request',
                                                 job_dict,
                                                 headers)
                self.logger.info(reqmgr_response)
                workflow_name = json.loads(reqmgr_response).get('result', [])[0].get('request')
                relval.set('workflows', [{'name': workflow_name}])
                relval.set('status', 'submitted')
                relval.add_history('submission', 'succeeded', 'automatic')
                relval_db.save(relval.get_json())
            except Exception:
                if reqmgr_response:
                    reqmgr_response = reqmgr_response.replace('\\n', '\n')

                self.__handle_error(relval,
                                    f'Error submitting {prepid} to ReqMgr2:\n{reqmgr_response}')
                return

            try:
                # Try to approve workflow (move to assignment-approved) after few seconds
                time.sleep(3)
                approve_response = connection.api('PUT',
                                                  f'/reqmgr2/data/request/{workflow_name}',
                                                  {'RequestStatus': 'assignment-approved'},
                                                  headers)
            except Exception as ex:
                self.logger.error('Error approving %s: %s', prepid, str(ex))

            connection.close()
            self.logger.info(approve_response)
            controller.force_stats_to_refresh([workflow_name])
            self.__handle_success(relval)

        controller.update_workflows(relval)
        self.logger.info('Successfully finished %s submission', prepid)
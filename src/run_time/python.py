import ast
import re
from typing import Callable, Dict, List

import param

from run_time import BaseCodeRunTime


class PythonValidatorError(Exception):
    """Exception raised when Python code validation fails."""

    pass


class PythonCodeRunTime(BaseCodeRunTime):
    """
    Python Code Runtime class for running python code dynamically

    Parameters
    ----------
    imports : str
        A string of Python import statements
    variables : dict
        A dictionary of variable names and their values
    function_name: str
        The name of the function to run
    validator : PythonValidator, optional
        A PythonValidator object to validate the code before running
    """

    def __init__(
        self,
        imports: str,
        variables: Dict[str, any],
        function_name: str = "eda_function",
        validator=None,
    ):
        self.imports = imports
        self.variables = variables
        self.function_name = function_name
        self.validator = validator
        self.namespace: dict = {}

        # Execute the import statements
        exec(self.imports, self.namespace)

        # Add the variables to the namespace
        for key, value in self.variables.items():
            self.namespace[key] = value

    def _compile_function(self, code: str, function_name: str):
        """
        Compile a Python function from a code block.

        Parameters
        ----------
        code : str
            The block of Python code to compile.
        function_name : str
            The name of the function to compile.

        Returns
        -------
        Callable
            The compiled function.
        """
        # Validate the code if a validator was provided
        if self.validator:
            self.validator.validate(code)

        # Compile the code
        exec(code, self.namespace)

        # Return the function
        return self.namespace[function_name]

    def run_code(self, code: str):
        """
        Compile and run a Python function from a code block.

        Parameters
        ----------
        code : str
            The block of Python code to compile.

        Returns
        -------
        any
            The output of the function.
        """

        # Compile the function
        function = self._compile_function(code, self.function_name)

        # Run the function with the variables as input arguments
        output = function(**self.variables)
        if output is None:
            raise PythonValidatorError(
                "The code does not return any output, please return an output."
            )
        return output


class PythonValidator:
    """
    Python Code Validator class for validating python code.

    Parameters
    ----------
    check_imports : bool, optional
        Whether to check for import statements in the code. Default is True.
    check_links : bool, optional
        Whether to check for links in the code. Default is True.
    check_save_funcs : bool, optional
        Whether to check for functions that might save data. Default is True.
    check_exec_eval : bool, optional
        Whether to check for usage of exec or eval. Default is True.
    """

    def __init__(
        self,
        check_imports: bool = True,
        check_links: bool = True,
        check_save_funcs: bool = True,
        check_exec_eval: bool = True,
    ):
        self.check_imports = check_imports
        self.check_links = check_links
        self.check_save_funcs = check_save_funcs
        self.check_exec_eval = check_exec_eval
        # Functions that might be used to save data
        self.save_funcs = ["open", "write", "save", "dump"]

    def validate(self, code: str):
        """
        Validate a Python code.

        Parameters
        ----------
        code : str
            The Python code to validate.

        Raises
        ------
        PythonValidatorError
            If any of the validation checks fail.
        """
        if self.check_imports:
            if any(
                isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom)
                for node in ast.walk(ast.parse(code))
            ):
                raise PythonValidatorError(
                    "The code contains import statements, which are not allowed. \
                        Only use the libraries provided in the prompt and do not import any other libraries."
                )

        if self.check_links:
            if re.search(r"https?://\S+|www\.\S+", code):
                raise PythonValidatorError(
                    "The code contains links, which are not allowed. \
                        Please remove the links from the code or change the PythonValidator configuration."
                )

        if self.check_save_funcs:
            if any(func in code for func in self.save_funcs):
                raise PythonValidatorError(
                    "The code contains functions that might be used to save data, which are not allowed.\
                        Please remove or rename the functions in code to something other than {}.".format(
                        self.save_funcs
                    )
                )

        if self.check_exec_eval:
            if "exec" in code or "eval" in code:
                raise PythonValidatorError(
                    "The code contains usage of exec or eval, which are not allowed.\
                                            Please remove the usage of exec or eval from the code."
                )

        return True

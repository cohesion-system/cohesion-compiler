"""Calling conventions are the interface between a workflow and a
function or service that it calls.

This includes function prologue/epilogue for generated Python
functions, and task states for calling those functions.

It also includes task state data params for calling existing lambda
functions.

"""
import ast
from typing import List

class CallingConvention:

    def prologue(self) -> List[ast.AST]:
        return None

    def epilogue(self) -> List[ast.AST]:
        return None

    def taskStateDataParams(self, arn: str, args: List[str]) -> dict:
        """Returns InputPath, Parameters, ResultPath, OutputPath"""
        return {}

    def taskStateResource(self, arn: str) -> str:
        return None


class LambdaWithEnvCC(CallingConvention):
    def prologue(self) -> List[ast.AST]:
        m = ast.parse("env = event['env']")
        return m.body
    
    def epilogue(self) -> List[ast.AST]:
        m = ast.parse("return { 'env': env }")
        return m.body

    def taskStateResource(self, arn: str) -> str:
        # the is the most direct approach, simply calling the lambda
        # as a task by its arn.  downside -- we don't get any debug
        # info, such as logs.  upside -- simpler data handling; maybe
        # more overhead?  Good for production use, not great for
        # dev/test.
        return arn
    
    def taskStateDataParams(self, arn: str, args: List[str]) -> dict:
        # turns out none of these matter when you're calling the lambda by arn
        return { "InputPath": None,
                 "Parameters": None,
                 "ResultPath": None,
                 "OutputPath": None }

class UserDefinedLambdaCC(CallingConvention):

    # no prologue/epilogue -- we dont have any control over the user's
    # lambda.  make sure this is never called.
    def prologue(self):
        raise Exception("internal compiler error")
    def epilogue(self):
        raise Exception("internal compiler error")
    
    def taskStateResource(self, arn: str) -> str:
        return arn
    def taskStateDataParams(self, arn: str, args: List[str]) -> dict:
        params = {}
        for a in args:
            params["%s.$" % a] = "$.env.%s" % a
        return { "Parameters": params }
    

class LambdaWithEnvDebugCC(LambdaWithEnvCC):
    # TODO: use the lambda:invoke service which give us debug logs, exceptions etc.
    pass

class UserDefinedLambdaDebugCC(UserDefinedLambdaCC):
    # TODO: use the lambda:invoke service which give us debug logs, exceptions etc.
    pass

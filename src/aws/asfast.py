"""AWS Step Functions AST (ASFAST).

The ASFAST is a straightforward representation of the Step Function
JSON, in Python objects.  This makes codegen pretty simple (transform
to dictionary and simply JSON pretty print), and all the interesting
stuff is in the CAST -> ASFAST transform.

The CAST -> ASFAST transform:

We assume the following about the CAST:

 . If, For, While statements are already simplified, i.e. their
   test/iterator arguments are lifted out into separate statement(s).

 . There are no PythonASTs in the CAST any more.  (They've all been
   lifted into Lambdas, so we only have Calls left.)

 . As a result, for example, the right hand side of an assignment
   statement is always a Call (or Map, or low level Task).

 . All variable references everywhere are into an `env` dictionary.

Transforms for control flow constructs are pretty straightforward --
`if` becomes `Choice`, `while` becomes a loop, `for` becomes a `Map`
state with concurrency=1, etc.

Managing state:

All state is in one giant `env` object.  This object is passed to
every ASF state.  That's the only way to do it -- ASF states can't
reach into any kind of global mutable state, so we have to thread the
state through the whole step function.  Once we do this, we can pretty
much think of the env object as mutable global state.

Note that an ASF state input is different from the input of the task
that the state invokes.  The state gets to write an InputPath and
specify a Parameters object to precisely define the task input in
terms of state input.

For lambda calls, we pass the whole env object into them.  This is not
strictly necessary, we could optimize this by analysing what the
function actually uses and only passing that.  But for now it's good
enough.  The downside is that the JSON ser/deser time can add up quite
a bit.

Function arguments, calling convention, return values.

Calls to generated lambdas:

Calls to pythonast-generated lambdas don't need arguments; they can
simply operate on the "global" state.  In other words, both the
argument and the return value is the whole env object.  ResultPath
would be simply `$.env`, i.e. the output replaces the whole env object.

Calls to existing lambdas: 

First off, these do not need the env state object.  

Second, We do have to give the user some control here, because they're
the only ones who know the lambda's interface (bit of a shame that
there's no aws-documented calling convention, oh well).

So we can have two equivalent flavors of such calls, keyword args and
a single dictionary.

  cohesion.Lambda.foo(a = 1, b = 2)

  cohesion.Lambda.foo({ 'a': 1, 'b': 2 })

We could do positional args when there's just one arg.

Multiple positional args present a problem: we don't know vars what to
assign the args to because we don't have access to the function
definition.  We could simply pass the whole array as an array -- but
we can't know whether that's what the function actually expects.
Maybe we call allow the user to set up some sort of file with the
function signature (kind of equivalent to a header file in the C
compiler world.)

For return values: 

Our job is to translate 

  `var = Call(...)`

such that `var` has the result of the Call.  For this, we can use
ASF's ResultPath.  Since the env object is in the input, the
ResultPath in this case would be `$.env.var`.

So finally, for existing lambda calls, the *state* will get the env
obj, the *task* will get a Parameters dict that pulls out the
variables as needed from `$.env`, the lambda will get just that dict,
the lambda will output one result value, and ResultPath will stick
that result value in the right place into the env object.

"""


import typing
import ast
import astor
import json
import gensym

from layoutState import LayoutState, Position
import cast
from aws import calling
import config

#
# State types
#
State_Task = "Task"
State_Choice = "Choice"
State_Pass = "Pass"
State_Wait = "Wait"
State_Succeed = "Succeed"
State_Fail = "Fail"
State_Parallel = "Parallel"
State_Map = "Map"

#
# Nodes
#
class ASFAST:
    """
    Base node type for AWS Step Function (ASF) AST.
    """
    def __init__(self):
        self.loc = cast.SourceLocation()
        self.locEnd = None

    def set_loc(self, node: cast.CAST):
        """Copy source location from node to self."""
        self.loc = node.loc
        if node.locEnd:
            self.locEnd = node.locEnd
        return self

class Module:
    """Collection of step functions."""
    def __init__(self, defs):
        super().__init__()
        self.defs = defs

    def to_dict(self):
        return [d.to_dict() for d in self.defs]


class State(ASFAST):
    def __init__(self, name, typ, comment):
        super().__init__()
        self.name = name
        self.typ = typ
        self.comment = comment
        self._layout = None

    def set_next(self, nxt: str):
        self.nxt = nxt
        self.end = False

    def set_end(self, end: bool):
        self.end = end
        if end and self.nxt and len(self.nxt) > 0:
            raise Exception("Internal Compiler Error, both next and end are set")

    def to_dict(self):
        d = {
            "Type": self.typ
        }
        if len(self.comment) > 0:
            d["Comment"] = self.comment
        if self._layout:
            d["_layout"] = {
                "row": self._layout.row,
                "column": self._layout.column
            }
        return d


class SleepState(State):
    def __init__(self, name, secondsPath):
        super().__init__(name, State_Wait, "")
        self.nxt = ""
        self.end = False
        self.secondsPath = secondsPath
    def to_dict(self):
        d = super().to_dict()
        if self.nxt and len(self.nxt) > 0:
            d["Next"] = self.nxt
        if self.end:
            d["End"] = self.end
        d["SecondsPath"] = self.secondsPath
        return d

class TaskState(State):
    def __init__(self, name, resource, nxt = "", end = False,
                 comment: str = "", inputPath: str = "$",
                 parameters: dict = None, resultPath: str = "$",
                 outputPath: str = "$",
                 timeoutSeconds: int = None,
                 heartbeatSeconds: int = None,
                 retry = None,
                 catch = None):
        super().__init__(name, State_Task, comment)
        self.nxt = nxt
        self.end = end
        self.resource = resource
        self.inputPath = inputPath
        self.parameters = parameters
        self.resultPath = resultPath
        self.outputPath = outputPath
        self.timeoutSeconds = timeoutSeconds
        self.heartbeatSeconds = heartbeatSeconds
        self.retry = retry
        self.catch = catch

    def to_dict(self):
        d = super().to_dict()
        if self.nxt and len(self.nxt) > 0:
            d["Next"] = self.nxt
        if self.end:
            d["End"] = self.end
        d["Resource"] = self.resource
        if self.inputPath and len(self.inputPath) > 0:
            d["InputPath"] = self.inputPath
        if self.parameters:
            d["Parameters"] = self.parameters
        d["OutputPath"] = self.outputPath
        d["ResultPath"] = self.resultPath
        if self.timeoutSeconds:
            d["TimeoutSeconds"] = self.timeoutSeconds
        if self.heartbeatSeconds:
            d["HeartbeatSeconds"] = self.heartbeatSeconds
        if self.retry:
            d["Retry"] = self.retry
        if self.catch:
            d["Catch"] = self.catch        
        return d

class ChoiceState(State):
    def __init__(self, name: str, choices, default: str, comment: str = ""):
        super().__init__(name, State_Choice, comment)
        self.choices = choices
        self.default = default

    def to_dict(self):
        d = super().to_dict()
        d["Choices"] = [c.to_dict() for c in self.choices]
        d["Default"] = self.default
        return d

class ChoiceRule(ASFAST):
    def __init__(self, boolExpr, nxt):
        super().__init__()
        self.boolExpr = boolExpr
        self.nxt = nxt
    def to_dict(self):
        d = self.boolExpr.to_dict()
        d["Next"] = self.nxt
        return d

class BoolExpr(ASFAST):
    pass

class TestBooleanVar(BoolExpr):
    def __init__(self, varName):
        super().__init__()
        self.varName = varName
    def to_dict(self):
        return { "Variable": self.varName,
                 "BooleanEquals": True }
            

class Map(State):
    pass
    
class LambdaState(TaskState):
    """
    Same as TaskState, except it's always a Lambda call.
    """
    pass


class StepFunction(ASFAST):
    """
    Step function definition.  Name, state list, start state.
    """
    def __init__(self, name, states: typing.List[State], comment: str = "", startState: str = None, timeoutSec: int = None):
        super().__init__()
        self.name = name
        self.comment = comment
        self.timeoutSec = timeoutSec
        self.states = states
        self.startState = startState
        if not self.startState:
            self.startState = self.states[0].name

    def validate(self):
        have_states = set([s.name for s in self.states])
        if self.startState not in have_states:
            raise Exception("Start state %s is not defined" % self.startState)
        for s in self.states:
            if s.nxt and s.end:
                raise Exception("State %s has next and also end" % s.name)
            if s.nxt not in self.states:
                raise Exception("State %s has next = %s but didn't state %s is undefined" % (s.name, s.nxt, s.nxt))

    def to_dict(self):
        d = ({
            "StartAt": self.startState,
            "States": {state.name: state.to_dict() for state in self.states}
        })
        if self.timeoutSec:
            d["TimeoutSeconds"] = self.timeoutSec
        return d

    def remove_layout(self):
        """Remove layout info from states, since it isn't valid step functions code"""
        for s in self.states:
            s._layout = None

    def graph(self):
        """Return a graph for visualization"""
        nodes = {}
        edges = []
        for s in self.states:
            pos = s._layout
            nodes[s.name] = {
                "row": pos.row,
                "column": pos.column,
                "srcmap": {
                    "loc": [s.loc.line, s.loc.col]
                    # future: add source file name (for now this works only for a single file input)
                }
            }
            if s.locEnd:
                nodes[s.name]["srcmap"]["locEnd"] = [s.locEnd.line, s.locEnd.col]

            # choice states are handled a bit differently
            if isinstance(s, ChoiceState):
                for rule in s.choices:
                    edges.append({'from': s.name, 'to': rule.nxt})
                edges.append({'from': s.name, 'to': s.default})
            else:
                if s.nxt and len(s.nxt) > 0:
                    edges.append({'from' : s.name, 'to': s.nxt})

                # handle catcher edges; s.catch is a list of catch clauses
                if isinstance(s, TaskState) and s.catch and len(s.catch) > 0:
                    for catcher in s.catch:
                        edges.append({
                            'from': s.name,
                            'to': catcher['Next'],
                            'type': 'catch'
                        })

        graph = { 'nodes': nodes, 'edges': edges }
        return graph

            

# class Catcher(ASFAST):
#     """
#     A single catcher; will be an element of a catcher list
#     """
#     def __init__(self, err: str, nxt: str, path: str):
#         self.err = err
#         self.nxt = nxt
#         self.path = path


class Pass(State):
    def __init__(self, name, inputPath: str = "",
                 parameters: dict = None, outputPath: str = "", nxt: str = "", end: bool = False):
        super().__init__(name, State_Pass, "")
        self.inputPath = inputPath
        self.parameters = parameters
        self.outputPath = outputPath
        self.nxt = nxt
        self.end = end

    def to_dict(self):
        d = super().to_dict()
        if len(self.inputPath) > 0:
            d["InputPath"] = self.inputPath
        if self.parameters:
            d["Parameters"] = self.parameters
        if len(self.outputPath) > 0:
            d["OutputPath"] = self.outputPath
        if self.nxt and len(self.nxt) > 0:
            d["Next"] = self.nxt
        if self.end:
            d["End"] = self.end
        return d

class RemovablePass(Pass):
    """We emit Pass nodes in some cases below, mostly to simplify the
    codegen.  We can eliminate those in another pass.

    """
    pass


class Break(Pass):
    """A break is a just a pass state with the .nxt property set to a
    certain state.

    We prevent set_next and set_end from doing anything -- this looks
    odd, but it makes transform_cast_sequence etc simpler since they
    don't have to special case anything.

    """
    def set_next(self, name: str):
        # do not set next; break already has a next.
        pass
    def set_end(self, end: bool):
        # don't allow end -- we always have a next
        pass


#
# CAST -> ASFAST Utils
#

class GenStateName:
    def __init__(self):
        self.used = set([])
    def gen(self, prefix: str) -> str:
        n = 0
        while True:
            if n == 0 and prefix and len(prefix) > 0:
                name = prefix
            else:
                name = "%s_%s" % (prefix, n)
            n += 1
            if name not in self.used:
                self.used.add(name)
                return name

genStateName = None


class Arn:
    """Keep track of accountID and region so we can generate lambda ARNs.

    """
    def __init__(self, region, accountID):
        self.region = region
        self.accountID = accountID

    def lambdaARN(self, name: str) -> str:
        """Given a function, return its ARN.

        """
        if name.startswith('arn:'):
            return name
        else:
            n = name.replace('_', '-')
            return 'arn:aws:lambda:%s:%s:function:%s' % (self.region, self.accountID, n)


    def activityARN(self, name: str) -> str:
        """Given an activity name, return its ARN.

        """
        if name.startswith('arn:'):
            return name
        else:
            n = name.replace('_', '-')
            return 'arn:aws:states:%s:%s:activity:%s' % (self.region, self.accountID, n)

        
arn = None




# def sequence(nodes: typing.List[ASFAST]) -> typing.List[ASFAST]:
#     """Turn a list of state nodes into a sequence of them, i.e. set the
#        `next` of each node to point to the one after it, and set
#        `end=true` for the last node.

#     """
#     n = len(nodes)
#     for i in range(n):
#         if not isinstance(nodes[i], State):
#             raise Exception("Sequence can only have States, found %s instead" %
#                             nodes[i].__class__.__name__)
#         if i == n - 1:
#             nodes[i].end = True
#             nodes[i].nxt = None
#         else:
#             nodes[i].nxt = nodes[i + 1].name
#             nodes[i].end = False
#     return nodes


def build(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    """
    WorkflowAST -> ASFAST; Python Functions -> Lambdas
    """
    init_state(cfg, agg)

    agg.workflowAst = transform_cast(agg.cast)
    
    return agg



# TODO: rewrite transform into a class

# Target stacks for break, continue, and exceptions
break_target_stack: typing.List[str] = None
continue_target_stack: typing.List[str] = None
exception_handler_stack = None
exception_handler_map = None
routerFunc = None
layoutState = None

def init_state(config: config.Config, agg: cast.Aggregate):
    """
    Init various bits of state for this pass
    """
    global break_target_stack 
    global continue_target_stack 
    global exception_handler_stack
    global exception_handler_map
    global genStateName
    global arn
    global routerFunc
    global layoutState
    
    break_target_stack = []
    continue_target_stack = []
    exception_handler_stack = []
    exception_handler_map = {}

    genStateName = GenStateName()

    arn = Arn(config.get("region"), config.get("account_id"))

    if config.get("use_router_func"):
        routerFunc = gensym.gensym("router")
    else:
        routerFunc = None

    layoutState = LayoutState()


def transform_cast(node: cast.CAST) -> typing.List[ASFAST]:
    """Transform a CAST node to a list of ASFAST nodes.

    To realize why the output is a list, consider cast.If.  We have to
    output a Choice state, and the whole thenBody and elseBody, and
    wire up the nxt states correctly.  For and while loops have to be
    handled similarly.

    Note that once this function is entered, there can be no more
    PythonASTs generated.  All Python stuff has to be lifted out into
    Lambdas before this transform.

    """
    
    if isinstance(node, cast.Module):
        return Module([s for n in node.body for s in transform_cast(n)])

    elif isinstance(node, cast.Def):
        # if the step func invocation input looks like:
        # { 'a': 42, 'b': 123, 'c': 'hi' }
        #
        # and the step function definition looks like:
        # def foo(a, b): ...
        #
        # Then the pass state below will get this input (and pass it to the next state):
        # 
        # { 'env': { 'a': 42, 'b': 123 } }
        initState = Pass(name = genStateName.gen("env_init"),
                         inputPath = "$",
                         parameters = { 'env' : {} })
        for a in node.args:
            initState.parameters['env']["%s.$" % a.name] = "$.%s" % a.name
            # TODO handle default values

        initState._layout = layoutState.get()
        initState.set_loc(node)
            
        states = [initState]
        bodyASF = transform_cast_sequence(node.body)
        initState.nxt = bodyASF[0].name
        states.extend(bodyASF)

        sfNode = StepFunction(name = node.name, states = states)
        sfNode.set_loc(node)
        return [sfNode]

    elif isinstance(node, cast.Assign):
        if isinstance(node.value, cast.Call):
            # TODO handle multi assignment
            return transform_cast_call(node = node.value, targetVar = node.target)
        else:
            raise Exception("Internal error: assignment of %s" % node.value.__class__.__name__)

    elif isinstance(node, cast.Call):
        # unassigned call (no target var to put the result in)
        return transform_cast_call(node = node, targetVar = None)
        
    elif isinstance(node, cast.If):
        return transform_cast_if(node)

    elif isinstance(node, cast.ForLoop):
        return transform_cast_for(node)

    elif isinstance(node, cast.WhileLoop):
        return transform_cast_while(node)

    elif isinstance(node, cast.Return):
        return transform_cast_return(node)

    elif isinstance(node, cast.Break):
        return transform_cast_break(node)

    elif isinstance(node, cast.Try):
        return transform_cast_try(node)
    
    else:
        raise Exception("Unhandled CAST node type: %s" % node.__class__.__name__)
    

def transform_cast_sequence(nodes: typing.List[cast.CAST]) -> typing.List[ASFAST]:
    result = []
    for n in nodes:
        n1 = transform_cast(n)
        if not n1:
            print("bad result: %s" % n)
        # attach start of n1 to end of current sequence
        if len(result) > 0:
            result[-1].nxt = n1[0].name
        else:
            # Nothing to do here. step function constructor above chooses
            # the first state as the start state.  other control flow
            # constructs explicitly set up nxt pointers.
            pass
        result.extend(n1)
    result[-1].set_end(True)
    return result

def transform_cast_call(node: cast.Call, targetVar: str) -> typing.List[ASFAST]:
    #
    # like other transforms, we assume the args are just names, and
    # all exprs have been lifted out already
    #
    func = node.func.split('.')
    if len(func) > 1:
        taskState = None
        if func[1] == 'Lambda': # cohesion.Lambda.<funcName>
            #
            # cohesion.Lambda.<fn> calls are calls to existing lambdas
            # that we don't control.  The state still gets the whole env,
            # but using `parameters`, we limit the input to the lambda.
            #
            funcName = func[-1]
            taskState = LambdaState(name = genStateName.gen(funcName),
                                    resource = arn.lambdaARN(funcName))
        elif func[1] == 'activity':
            activityName = func[-1]
            taskState = TaskState(name = genStateName.gen(activityName),
                                  resource = arn.activityARN(activityName))
        elif func[1] == 'sleep':
            taskState = SleepState(name = genStateName.gen("sleep"),
                                   secondsPath = "$.env." + node.args[0])
            taskState._layout = layoutState.get()
            taskState.set_loc(node)
            return [taskState]
        elif func[1] == 'task': # cohesion.task
            raise Exception("cohesion.task unimplemented")


        # Set up inputpath, resultpath, parameters
        if targetVar:
            taskState.resultPath = "$.env.%s" % targetVar
        else:
            # We have to discard the output, but still pass thru the
            # input data. This is kinda tricky -- I can't figure out a
            # way to do this without an additional pass state. For now
            # we just dump it into a variable called "discard".
            taskState.resultPath = "$.env.discard"
                
            # TODO: for now we just implement a single positional argument
            if len(node.args) > 0:
                taskState.inputPath = "$.env." + node.args[0]
            else:
                # make sure the lambda gets no input (is this right?)
                taskState.parameters = {}
                
        # Retry
        if node.retry:
            # todo validate?
            taskState.retry = node.retry

        # Catch: generate catchers if we are inside a try
        global exception_handler_map
        if len(exception_handler_map) > 0:
            catchers = []
            for typ, stateName in exception_handler_map.items():
                catcher = {}
                catcher["ErrorEquals"] = [typ]
                catcher["Next"] = stateName
                catchers.append(catcher)
            taskState.catch = catchers

        # Add layout
        taskState._layout = layoutState.get()
        taskState.set_loc(node)
            
        return [taskState]
        
        
    else:
        global routerFunc
        if routerFunc:
            ls = LambdaState(name = genStateName.gen(node.func),
                             resource = arn.lambdaARN(routerFunc),
                             parameters = {
                                 "env": "$.env",
                                 "func": node.func
                             })
            ls._layout = layoutState.get()
            ls.set_loc(node)
            return [ls]
        else:
            #
            # This function call is is cohesion-generated, so we need to
            # pass/return the whole env object.
            #
            ls = LambdaState(name = genStateName.gen(node.func),
                             resource = arn.lambdaARN(node.func))
            ls._layout = layoutState.get()
            ls.set_loc(node)
            return [ls]

def transform_cast_if(node: cast.If) -> typing.List[ASFAST]:
    # at this point the test MUST be a simple variable load, and we
    # expect the var to already be a bool. so before this we need a
    # pass that does `if(expr)` => `tmp = bool(expr); if(tmp)...`
    #testVar = astor.to_source(node.test).rstrip()
    testVar = node.test.slice.value.s
    choiceNode = ChoiceState(
        name = genStateName.gen("choice"),
        choices = [ChoiceRule(boolExpr = TestBooleanVar("$.env." + testVar),
                              nxt = "")],
        default = "")

    choiceNode._layout = layoutState.get()
    choiceNode.set_loc(node)
    
    # for simplicity we add a dummy "pass" node, and use it as the
    # next-state for both then and else bodies.  this lets us a
    # have a single "exit" node which can then be wired up to
    # whatever is next.
    passNode = RemovablePass(genStateName.gen("if_pass"), "")

    # layout column for then body
    layoutState.push_column()

    # then
    thenBodyASF = transform_cast_sequence(node.thenBody)
    choiceNode.choices[0].nxt = thenBodyASF[0].name
    thenBodyASF[-1].set_next(passNode.name)

    # pop the column for the then body
    thenPos = layoutState.pop()
    
    # else (stays in the same column as then body)
    elseBodyASF = None
    choiceNode.default = passNode.name
    if node.elseBody:
        elseBodyASF = transform_cast_sequence(node.elseBody)
        choiceNode.default = elseBodyASF[0].name
        elseBodyASF[-1].set_next(passNode.name)

    # Update layout state to lower row of the two columns (then/else)
    layoutState.updateRow(thenPos)

    # passNode is at the bottom
    passNode._layout = layoutState.get()
    # passNode doesn't actually have a location, so options are: (a)
    # no mapped location (b) first line of next state (c) start of
    # if-statement.  I really have no idea which is best, going with
    # (c) for now; let's decide based on user feedback and how it
    # "feels".
    passNode.set_loc(node)
        
    # build up the result
    result = [choiceNode]
    result.extend(thenBodyASF)
    if elseBodyASF:
        result.extend(elseBodyASF)
    result.append(passNode)
    return result

def transform_cast_for(node: cast.ForLoop) -> typing.List[ASFAST]:
    # TODO translate this to a Map state with concurrency=1, and
    # result discarded
    raise Exception("for loop not implemented")


def transform_cast_while(node: cast.WhileLoop) -> typing.List[ASFAST]:
    # We assume that the test has been lifted out and is now just a bool var name.
    # As usual we use a removable pass node to make codegen easier.
    # choicestate(choice(test, body.firstnode), default=passnode), body, passnode
    
    startPassNode = RemovablePass(genStateName.gen("loop_start"),
                                      nxt = "", end = False)
    startPassNode._layout = layoutState.get()
    startPassNode.set_loc(node)

    endPassNode = RemovablePass(genStateName.gen("loop_end"),
                                nxt = "", end = False)
    continue_target_stack.append(startPassNode)
    break_target_stack.append(endPassNode)

    bodyASF = transform_cast_sequence(node.body)

    break_target_stack.pop()
    continue_target_stack.pop()

    endPassNode._layout = layoutState.get()
    endPassNode.set_loc(node) # unclear if good. see the comment near the if_pass node
    
    if isinstance(node.test, ast.NameConstant) and node.test.value == True:
        # This compilation has no choice state, because the loop test
        # is constant.  The only way to exit this loop would be an
        # exit within the body (break/return/failure).
        # [startPassNode, ...body, endPassNode]
        startPassNode.set_next(bodyASF[0].name)
        bodyASF[-1].set_next(startPassNode.name)
        result = [startPassNode]
        result.extend(bodyASF)
        result.append(endPassNode)
        return result
    else:
        # currently dead code:
        testVar = cast.varFromEnv(node) # equivalent to testVar = node.test.slice.value.s
        choiceNode = ChoiceState(
            name = genStateName.gen("while_test"),
            choices = [ChoiceRule(boolExpr = TestBooleanVar("$.env." + testVar),
                                  nxt = bodyASF[0].name)],
            default = endPassNode.name)
        bodyASF[-1].set_next(choiceNode.name)
        result = [choiceNode]
        result.extend(bodyASF)
        result.append(endPassNode)
        return result
    
def transform_cast_return(node: cast.Return) -> typing.List[ASFAST]:
    varName = node.value
    passNode = Pass(name = genStateName.gen("exit_pass"),
                    #parameters = { "result.$": "$.env.%s" % varName },
                    inputPath = "$.env.%s" % varName,
                    end = True)
    passNode._layout = layoutState.get()
    passNode.set_loc(node)
    return [passNode]


def transform_cast_break(node: cast.Break) -> typing.List[ASFAST]:
    breakNode = Break(name = genStateName.gen("break"),
                      nxt = break_target_stack[-1].name)
    breakNode._layout = layoutState.get()
    breakNode.set_loc(node)
    return [breakNode]

class HandlerReference:
    """A wrapper for the handler to place on the exception stack.  Keeps
    track of the state name of the handler body."""
    def __init__(self, handler: cast.handler, stateName: str):
        self.handler = handler
        self.stateName = stateName

def transform_cast_try(node: cast.Try) -> typing.List[ASFAST]:
    # Consider a world with only one exception type.  In this world
    # we'd maintain a stack of handlers -- and for each task we'll add
    # one catcher pointing at the one handler that's on top of the
    # stack.
    #
    # Now consider multiple exception types.  We'll still maintain
    # only one stack, but each handler has an error type it handles.
    # For each task invoked, we'll walk the stack, and make a map of
    # handlers -- from each error type to the handler for that type
    # that's highest on the stack.
    #
    # And, we have to handle control flow -- i.e. a failed task with
    # an exception handler should fall through to whatever's after the
    # try/except.  In this regard an exception is try/except is just
    # like a loop break -- we can add a pass state after whole
    # try/except block, and set up all handlers fall through to that
    # state.
    #

    # Node arrangement in the output:
    # body <jmp endPass> handlerbody1 <jmp endPass> handlerbody2 <jmp endPass> .... endPass
    
    # the end state that everything will jump to
    endPass = RemovablePass(name = genStateName.gen("endTry"),
                            nxt = "", end = False)

    # push temporary layout state for handlers, since we're generating
    # them out of order we'll fix them later.
    layoutState.push(Position(row=1, column=1 + layoutState.peek().column))
    
    # transform each handler body
    handlerBodies = []
    for h in node.handlers:
        handlerBody = transform_cast_sequence(h.body)
        handlerBody[-1].set_next(endPass.name)
        handlerBodies.append(handlerBody)
        handlerRef = HandlerReference(h, handlerBody[0].name)
        exception_handler_stack.append(handlerRef)

    # back to the real layout
    layoutState.pop()
        
    # Now we make the handler map -- one handler ref per type. We
    # start from the bottom of the stack so that the top wins.
    global exception_handler_map
    exception_handler_map = {}
    for hr in exception_handler_stack:
        for typ in hr.handler.types:
            exception_handler_map[typ] = hr.stateName

    # finally we're ready to transform the body
    body = transform_cast_sequence(node.body)
    body[-1].set_next(endPass.name)

    # layout fixups: place the handler bodies below the main body
    nRows = body[-1]._layout.row
    lastRow = 0
    for b in handlerBodies:
        for s in b:
            s._layout.move_down(nRows)
            lastRow = s._layout.row
    layoutState.updateRow(Position(lastRow, 0))

    # end pass node layout update
    endPass._layout = layoutState.get()
    endPass.set_loc(node)
    
    # pop all handlers that we pushed onto exception_handler_stack
    for i in range(len(node.handlers)):
        exception_handler_stack.pop()
    # clean up exception_handler_map
    exception_handler_map = {}
    
    # arrange the body, handler bodies, and endPass 
    result = []
    result.extend(body)
    for hb in handlerBodies:
        result.extend(hb)
    result.append(endPass)

    # All done
    return result

        

#def transform_cast_continue(node: cast.Continue) -> typing.List[ASFAST]:
#    continueNode = Continue(name = genStateName.gen("continue"),
#                            nxt = continue_target_stack[-1].name)
#    return [continueNode]

def dump(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    print(dump_asfast(agg.workflowAst))
    return agg

def dump_asfast(node: ASFAST) -> str:
    if isinstance(node, Module):
        return ("\n".join([dump_asfast(n) for n in node.defs]) + "\n")
    elif isinstance(node, StepFunction):
        return (("StepFunction(name = %s):\n" % node.name) +
                "\n".join([dump_asfast(state) for state in node.states]) +
                "\n")
    elif isinstance(node, TaskState):
        m = ("Task(name = %s, resource = %s" % (node.name, node.resource))
        if node.end:
            m += ", END"
        elif node.nxt:
            m += ", next = %s" % node.nxt
        m += ")\n"
        return m
    elif isinstance(node, ChoiceState):
        return "Choice(name = %s, choices = %s, default = %s)\n" % \
            (node.name, dump_asfast(node.choices[0]), node.default)
    elif isinstance(node, ChoiceRule):
        return "ChoiceRule(%s)" % node.to_dict()
    elif isinstance(node, RemovablePass):
        return "RemovablePass(name = %s, next = %s)" % (node.name, node.nxt)
    elif isinstance(node, Pass):
        return "Pass(name = %s, next = %s)" % (node.name, node.nxt)
    else:
        return "not implemented: %s\n" % node.__class__.__name__



#
# Extract graphs out of the ASFAST 
#
def build_graphs(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    for asf in agg.workflowAst.defs:
        agg.workflowGraphs[asf.name] = asf.graph()
        asf.remove_layout()
    return agg


def remove_state_refs(asf: StepFunction, stateName, replacement):
    """Remove references to stateName, changing them to point at
    replacement instead.  If replacement is None, try to end the
    workflow at states that goto stateName; but if those states are
    not terminable, removal fails.

    Returns true on success.

    """
    failed = False
    for s in asf.states:
        if 'nxt' in dir(s):
            if s.nxt == stateName:
                if replacement:
                    s.nxt = replacement
                    s.end = False
                else:
                    if isinstance(s, Break):
                        failed = True
                    else:
                        s.nxt = None
                        s.set_end(True)
        if isinstance(s, ChoiceState):
            for cr in s.choices:
                if cr.nxt == stateName:
                    if replacement:
                        cr.nxt = replacement
                    else:
                        failed = True

            if s.default == stateName:
                if replacement:
                    s.default = replacement
                else:
                    failed = True 
    return not failed

#
# Eliminate removable pass states
#
def remove_pass(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    removedStates = []
    for asf in agg.workflowAst.defs:
        # Find states to remove put them in removedStates
        for state in asf.states:
            if isinstance(state, RemovablePass):
                next_state = state.nxt                
                success = remove_state_refs(asf, state.name, next_state)
                if success:
                    removedStates.append(state)

        # Actually remove the states
        rsNames = [s.name for s in removedStates]
        newStates = [s for s in asf.states if s.name not in rsNames]
        asf.states = newStates

        # Fix layout
        # we look for "missing rows" and simply move everything up
        # the missing rows can only come from removedStates, so we use those states to find such rows
        # (we have to do this with the lowest row first, so sort accordingly)
        for rs in sorted(removedStates, key=(lambda s: -1 * s._layout.row)):
            if not rs._layout:
                continue
            removedRow = rs._layout.row
            # is this row missing in the new asf?
            inThisRow = [s for s in asf.states if s._layout and s._layout.row == removedRow]
            if len(inThisRow) == 0:
                # this row is empty: move everything that's below it up by one row
                for s in asf.states:
                    if s._layout and s._layout.row > removedRow:
                        s._layout.row -= 1
    return agg


#
# JSON emitter
#
def emit_json(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:

    """
    Emit each step function in to a JSON file in outdir/stepfunc-NAME.json
    """

    outdir = cfg.get('output_dir')
    for asf in agg.workflowAst.defs:
        with open("%s/%s.sfn.json" % (outdir, asf.name), "w") as f:
            f.write(json.dumps(asf.to_dict(), indent=4, separators=(',', ': ')))

    # emit graphs
    for wfName in agg.workflowGraphs.keys():
        graph = agg.workflowGraphs[wfName]
        with open("%s/%s.graph.json" % (outdir, wfName), "w") as f:
            f.write(json.dumps(graph, indent=4, separators=(',', ': ')))

    return agg


def generate_router_func(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    """Generate one router function for all the python functions.

    This allows us to emit all the generated python functions into one python module,
    and one lambda, 

    """

    if not cfg.get("use_router_func"):
        return agg

    # don't generate router if there are zero lambdas
    if len(agg.pythonFunctions) == 0:
        return agg
    
    global routerFunc
    funcNode = (ast.parse("""
def %s(event, context):
    funcName = event['func']
    func = globals()[funcName]
    return func(event, context)
    """ % routerFunc)).body[0]

    agg.addPythonFunction(funcNode)
    agg.pythonRouterFuncName = routerFunc
    
    return agg



def wrap_lambdas(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    """Emit each of the cloud functions wrapped in an interface that
    makes sense as an AWS Lambda called by step functions.

    We pass the env JSON in and out of the lambdas.

    """
    # figure out calling convention (debug mode cc results in more
    # info thru the step fn api)
    cc = calling.LambdaWithEnvCC()
    if cfg.get('debug_mode'):
        cc = calling.LambdaWithEnvDebugCC()

    for funcName in agg.pythonFunctions:
        funcDef = agg.pythonFunctions[funcName]
        body = funcDef.body
        newBody = cc.prologue() + body + cc.epilogue()
        funcDef.body = newBody

        # add to cloud functions
        agg.cloudFunctions[funcName] = funcDef

    return agg

    

def emit_lambdas(cfg: config.Config, agg: cast.Aggregate) -> cast.Aggregate:
    """Put the Lambdas into a module, and emit it to a source file.
    
    """
    path = "%s/functions.py" % cfg.get("output_dir")
    with open(path, "w") as f:
        for funcName in agg.cloudFunctions:
            funcNode = agg.cloudFunctions[funcName]
            src = astor.to_source(funcNode)
            f.write(src)
            f.write("\n\n")
            
    return agg

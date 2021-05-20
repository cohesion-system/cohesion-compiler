import typing
import copy

class Position:
    def __init__(self, row: int, column: int):
        self.row = row
        self.column = column

    def move_down(self, n):
        self.row += n
        
    def inc_row(self):
        self.row += 1

    def copy(self):
        return copy.copy(self)
        
def rowWiseMax(pos1: Position, pos2: Position):
    """Return the row-wise max of two positions (i.e. the lower one)"""
    if pos1.row >= pos2.row:
        return pos1
    else:
        return pos2    
        
class LayoutState:
    def __init__(self):
        self.layoutStack = []
        pos = Position(0, 0)
        self.push(pos)

    def push(self, pos: Position):
        self.layoutStack.append(pos)

    def get(self) -> Position:
        """Returns a position and increments the current row"""
        pos = self.peek().copy()
        self.layoutStack[-1].inc_row()
        return pos
        
    def push_column(self) -> Position:
        pos = self.peek().copy()
        pos.column += 1
        self.layoutStack.append(pos)
        return pos
        
    def peek(self) -> Position:
        return self.layoutStack[-1]

    def updateRow(self, pos: Position):
        """Update current position row to pos.row if needed"""
        t = self.peek()
        if pos.row > t.row:
            t.row = pos.row
    
    def pop(self) -> Position:
        if len(self.layoutStack) == 1:
            # stack underflow
            raise Error("Layout stack error: can't pop last")
        return self.layoutStack.pop()

    # def new_column(self) -> NewColumnCtxMgr:
    #     """A context manager with the new column on the stack"""
    #     return NewColumnCtxMgr(self)


# class NewColumnCtxMgr:
#     def __init__(self, ls):
#         self.ls = ls
#     def __enter__(self):
#         pos = ls.push_column()
#         return pos
#     def __exit__(self, typ, value, tb):
#         ls.pop()

import abstract.semantics as semantic
import abstract.tree as coolAst
import typecheck.visitor as visitor
from travels.context_actions import update_attr_type, update_method_param, update_scope_variable
from typing import Optional

void = semantic.VoidType()


class TypeInferer:
    """
    Para inferir los tipos en un programa se aprovecha el AST devuelto al evaluar el parse de dicho programa.
    Para este propósito, se toma el programa como una gran expresión, y entonces se realiza un recorrido en bottom-up
    para inferir los tipos de las subexpresiones que sean necesarias. Empezando por las hojas que corresponden a las constantes
    y tipos previamente definidos, que por supuesto ya tienen su tipo bien calculado, se procede a ir subiendo por el árbol
    calculando el tipo de cada subexpresión en dependencia de su regla funcional y de los tipos previamente calculados
    en el contexto del programa. Como ejemplo tomemos el de la expresion  "if bool then e1 else e2":

    La regla de dicha expresion se puede representar como :
    C|-bool: BOLEAN, C|-e1:T1, C|-e2:T2
    --------------------------------------
        C|- if bool then e1 else e2: T3
    donde T1 <= T2 <= T3.

    O sea que si en el contexto conocemos el tipo de e1 y el de e2 y además aseguramos que bool es una expresión de tipo
    BOLEAN entonces el tipo de la expresión completa sera el Ancestro Común Mas Cercano  a los tipos T1 y T2, o en otras palabras,
    el menor tipo T3 tal que T1 se conforme en T3 y T2 se conforme en T3.
    """
    def __init__(self, context: semantic.Context, errors=[]):
        self.context: semantic.Context = context
        self.current_type: Optional[semantic.Type] = None
        self.INTEGER = self.context.get_type('int')
        self.OBJECT = self.context.get_type('object')
        self.STRING = self.context.get_type('string')
        self.BOOL = self.context.get_type('bool')
        self.AUTO_TYPE = self.context.get_type('AUTO_TYPE')
        self.errors = errors
        self.current_method: Optional[semantic.Method] = None

    @visitor.on('node')
    def visit(self, node, scope, infered_type=None):
        pass

    # --------------------------------------------------------------------------------------------------------------------------#
    # -----------------------------------------------------EXPRESIONES----------------------------------------------------------#
    # --------------------------------------------------------------------------------------------------------------------------#

    # ---------------------------------------------------------------
    # Calcular todos los tipos en el contexto del programa.        |
    # ---------------------------------------------------------------
    @visitor.when(coolAst.ProgramNode)  #type: ignore  # noqa
    def visit(self, node, scope=None, infered_type=None, deep=1):  # noqa: F811
        program_scope = semantic.Scope() if scope is None else scope
        print(f"Este es el scope en la vuelta {deep} :\n {program_scope}")
        if deep == 1:
            for class_ in node.class_list:
                self.visit(class_, program_scope.create_child())
        else:
            for class_, child_scope in zip(node.class_list, program_scope.children):
                self.visit(class_, child_scope, deep=deep)
        return program_scope

    # -----------------------------------------------------------------
    # Calcular los tipos en esta clase, visitar primero los atributos |
    # y luego los métodos para garantizar que al revisar los métodos  |
    # ya todos los atributos estén definidos en el scope.             |
    # -----------------------------------------------------------------
    @visitor.when(coolAst.ClassDef)  #type: ignore  # noqa
    def visit(self, node, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        self.current_type = self.context.get_type(node.idx)
        for feature in node.features:
            if isinstance(feature, coolAst.AttributeDef):
                self.visit(feature, scope, deep=deep)
        if deep == 1:
            for feature in node.features:
                if isinstance(feature, coolAst.MethodDef):
                    self.visit(feature, scope.create_child(), deep=deep)
        else:
            methods = (f for f in node.features if isinstance(f, coolAst.MethodDef))
            for feature, child_scope in zip(methods, scope.children):
                self.visit(feature, child_scope, deep=deep)

    # ---------------------------------------------------------
    # Definir un atributo en el scope.                        |
    # ---------------------------------------------------------
    @visitor.when(coolAst.AttributeDef)  #type: ignore  # noqa
    def visit(self, node: coolAst.AttributeDef, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        atrib = self.current_type.get_attribute(node.idx)
        if deep == 1:
            scope.define_variable(atrib.name, atrib.type)

    # ---------------------------------------------------------------------
    # Si el método no tiene un tipo definido, entonces tratar de inferir  |
    # su tipo en dependencia del tipo de su expresién de retorno.         |
    # Notar que al revisar el body del método se pueden inferir también   |
    # los argumentos que no hayan sido definidos con tipos específicos.   |
    # ---------------------------------------------------------------------
    @visitor.when(coolAst.MethodDef)  #type: ignore  # noqa
    def visit(self, node: coolAst.MethodDef, scope, infered_type=None, deep=1):  # noqa: F811
        print(node.idx)
        method = self.current_type.get_method(node.idx)
        self.current_method = method
        for param in node.param_list:
            self.visit(param, scope, deep=deep)

        last = None
        for statement in node.statements:
            last = self.visit(statement, scope, deep=deep)
        if not method.return_type != self.AUTO_TYPE:
            print(f'Infered type {last.name} for {node.idx}')
            method.return_type = last
        else:
            if not last.conforms_to(method.return_type):
                self.errors.append(f'Method {method.name} cannot return {last}')
        print(scope)

    @visitor.when(coolAst.Param)  #type: ignore  # noqa
    def visit(self, node: coolAst.Param, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        type_ = self.context.get_type(node.type)
        if deep == 1:
            scope.define_variable(node.id, type_)

    # -------------------------------------------------------------------------
    # Checkear si la variable a la que se le va a asignar el resultado de la  |
    # expresión tiene un tipo bien definido: en caso de tenerlo, verificar que|
    # el tipo de la expresión coincide con el tipo de la variable, de lo con- |
    # trario asignarle a la variable el tipo de retorno de la expresión.      |
    # -------------------------------------------------------------------------
    @visitor.when(coolAst.AssignNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.AssignNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        var_info = scope.find_variable(node.idx)
        if var_info:
            e = self.visit(node.expr, scope, infered_type)
            if var_info.type == self.AUTO_TYPE:
                print(f'Infered type {e.name} for {node.idx}')
                var_info.type = e
                if not scope.is_local(var_info.name):
                    update_attr_type(self.current_type, var_info.name, var_info.type)
                else:
                    update_method_param(self.current_type, self.current_method.name, var_info.name, var_info.type)
                update_scope_variable(var_info.name, e, scope)
                return void
            else:
                if not e.conforms_to(var_info.type):
                    self.errors.append(f'Expresion of type {e.name} cannot be assigned to variable {var_info.name} of type {var_info.type.name}')
                return void
        else:
            self.errors.append(f'Undefined variable name: {node.idx}')

    @visitor.when(coolAst.VariableCall)  #type: ignore  # noqa
    def visit(self, node, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        var_info = scope.find_variable(node.idx)
        if var_info:
            if infered_type and var_info.type == self.AUTO_TYPE:
                print(f'Infered type {infered_type.name} for {var_info.name}')
                var_info.type = infered_type
                if not scope.is_local(var_info.name):
                    update_attr_type(self.current_type, var_info.name, var_info.type)
                else:
                    update_method_param(self.current_type, self.current_method.name, var_info.name, var_info.type)
                update_scope_variable(var_info.name, infered_type, scope)
            return var_info.type
        else:
            self.errors.append(f'Name {node.idx} is not define.')

    @visitor.when(coolAst.IfThenElseNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.IfThenElseNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        cond = self.visit(node.cond, scope, infered_type, deep)
        e1 = self.visit(node.expr1, scope, infered_type, deep)
        e2 = self.visit(node.expr2, scope, infered_type, deep)
        if cond != self.BOOL:
            self.errors.append(f'Se esperaba una expresion de tipo bool y se obtuvo una de tipo {cond}.')
        if e1.conforms_to(e2):
            return e2
        elif e2.conforms_to(e1):
            return e1
        else:
            e1_parent = e1.parent
            e2_parent = e2.parent
            while e2_parent != e1_parent:
                e1_parent = e1_parent.parent
                e2_parent = e2_parent.parent
            return e1_parent

    @visitor.when(coolAst.VariableDeclaration)  #type: ignore  # noqa
    # TODO FIX THIS, IT is not working after change in grammar, REIMPLEMENT IT!!!!
    def visit(self, node: coolAst.VariableDeclaration, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        for var_idx, var_type, var_init_exp in node.var_list:
            type_ = self.context.get_type(var_type)
            if type_ != self.AUTO_TYPE:
                if deep == 1:
                    scope.define_variable(var_idx, type_)
            else:
                if deep == 1:
                    type_ = self.visit(node.block_statements, scope, infered_type, deep)
                    print(f'Infered type {type_.name} for {var_idx}')
                    scope.define_variable(node.idx, type_)
        return void

    @visitor.when(coolAst.FunCall)  #type: ignore  # noqa
    def visit(self, node: coolAst.FunCall, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        if isinstance(node.obj, semantic.Type):
            method = node.obj.get_method(node.id)
        elif node.obj == 'self':
            method = self.current_type.get_method(node.id)
        else:
            method = self.context.get_type(node.obj).get_method(node.id)

        for arg in node.args:
            self.visit(arg, scope, infered_type, deep)

        if method.return_type != self.AUTO_TYPE:
            return method.return_type
        elif infered_type:
            print(f'Infered type {infered_type.name} for {node.id}')
            method.return_type = infered_type
            return infered_type
        else:
            return self.AUTO_TYPE

    @visitor.when(coolAst.InstantiateClassNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.InstantiateClassNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        ret_type = self.context.get_type(node.type_)
        if ret_type in (self.AUTO_TYPE, void, self.STRING, self.INTEGER, self.OBJECT, self.BOOL):
            self.errors.append(f'Cannot instantiate {ret_type}')
        return ret_type

    @visitor.when(coolAst.WhileBlockNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.WhileBlockNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        ret_type = None
        for st in node.statements:
            ret_type = self.visit(st, scope, infered_type, deep)
        return ret_type

    # ---------------------------------------------------------------------------------------------------------------------------#
    # ---------------------------------------OPERACIONES ARITMÉTICAS-------------------------------------------------------------#
    # ---------------------------------------------------------------------------------------------------------------------------#


# -------------------------------------------------------------------------------------------------
# Todas las operaciones aritméticas estan definidas solamente para los enteros, luego, de checkeo|
# de cada operación se realiza evaluando sus operandos y viendo si sus tipos son consistentes con|
# INTEGER.                                                                                       |
# -------------------------------------------------------------------------------------------------

    @visitor.when(coolAst.PlusNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.PlusNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, self.INTEGER, deep)
        right = self.visit(node.right, scope, self.INTEGER, deep)
        if left.conforms_to(self.INTEGER) and right.conforms_to(self.INTEGER):
            return self.INTEGER
        else:
            self.errors.append(f'Invalid operation :{left.name} + {right.name}')
            return self.INTEGER

    @visitor.when(coolAst.DifNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.DifNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, self.INTEGER, deep)
        right = self.visit(node.right, scope, self.INTEGER, deep)
        if left.conforms_to(self.INTEGER) and right.conforms_to(self.INTEGER):
            return self.INTEGER
        else:
            self.errors.append(f'Invalid operation :{left.name} - {right.name}')
            return self.INTEGER

    @visitor.when(coolAst.DivNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.DivNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, self.INTEGER, deep)
        right = self.visit(node.right, scope, self.INTEGER, deep)
        if left.conforms_to(self.INTEGER) and right.conforms_to(self.INTEGER):
            return self.INTEGER
        else:
            self.errors.append(f'Invalid operation :{left.name} / {right.name}')
            return self.INTEGER

    @visitor.when(coolAst.MulNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.MulNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, self.INTEGER, deep)
        right = self.visit(node.right, scope, self.INTEGER, deep)
        if left.conforms_to(self.INTEGER) and right.conforms_to(self.INTEGER):
            return self.INTEGER
        else:
            self.errors.append(f'Invalid operation :{left.name} * {right.name}')
            return self.INTEGER

    # -------------------------------------------------------------------------------------------#
    # -----------------------------------OPERACIONES COMPARATIVAS -------------------------------#
    # -------------------------------------------------------------------------------------------#

    # ---------------------------------------------------------------------------------------------
    # Para poder comparar dos expresiones, estas deben ser del mismo tipo. El tipo de retorno de |
    # toda operación comparativa es BOOLEAN.                                                     |
    # ---------------------------------------------------------------------------------------------
    @visitor.when(coolAst.GreaterThanNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.GreaterThanNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, infered_type, deep)
        right = self.visit(node.right, scope, infered_type, deep)
        if left == right or left == self.AUTO_TYPE or right == self.AUTO_TYPE:
            return self.BOOL
        else:
            self.errors.append(f'Invalid operation: {left.name} > {right.name}')
            return self.BOOL

    @visitor.when(coolAst.GreaterEqualNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.GreaterEqualNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, infered_type, deep)
        right = self.visit(node.right, scope, infered_type, deep)
        if left == right or left == self.AUTO_TYPE or right == self.AUTO_TYPE:
            return self.BOOL
        else:
            self.errors.append(f'Invalid operation: {left.name} >= {right.name}')
            return self.BOOL

    @visitor.when(coolAst.LowerThanNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.LowerThanNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, infered_type, deep)
        right = self.visit(node.right, scope, infered_type, deep)
        if left == right or left == self.AUTO_TYPE or right == self.AUTO_TYPE:
            return self.BOOL
        else:
            self.errors.append(f'Invalid operation: {left.name} < {right.name}')
            return self.BOOL

    @visitor.when(coolAst.LowerEqual)  #type: ignore  # noqa
    def visit(self, node: coolAst.LowerEqual, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, infered_type, deep)
        right = self.visit(node.right, scope, infered_type, deep)
        if left == right or left == self.AUTO_TYPE or right == self.AUTO_TYPE:
            return self.BOOL
        else:
            self.errors.append(f'Invalid operation: {left.name} <= {right.name}')
            return self.BOOL

    @visitor.when(coolAst.EqualToNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.EqualToNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        left = self.visit(node.left, scope, infered_type, deep)
        right = self.visit(node.right, scope, infered_type, deep)
        if left == right or left == self.AUTO_TYPE or right == self.AUTO_TYPE:
            return self.BOOL
        else:
            self.errors.append(f'Invalid operation: {left.name} == {right.name}')
            return self.BOOL

    @visitor.when(coolAst.NotNode)  #type: ignore  # noqa
    def visit(self, node: coolAst.NotNode, scope: semantic.Scope, infered_type=None, deep=1):  # noqa: F811
        val_type = self.visit(node.lex, scope, infered_type, deep)
        if val_type == self.AUTO_TYPE or val_type == self.BOOL:
            return self.BOOL
        else:
            self.errors.append(f'Invalid operation: ! {val_type.name}')
            return self.BOOL

    # -----------------------------------------------------------------------------------------------------------------------#
    # --------------------------------------------------CONSTANTES-----------------------------------------------------------#
    # -----------------------------------------------------------------------------------------------------------------------#

    @visitor.when(coolAst.IntegerConstant)  #type: ignore  # noqa
    def visit(self, node, scope, infered_type=None, deep=1):  # noqa: F811
        return self.INTEGER

    @visitor.when(coolAst.StringConstant)  #type: ignore  # noqa
    def visit(self, node, scope, infered_type=None, deep=1):  # noqa: F811
        return self.STRING

    @visitor.when(coolAst.TrueConstant)  #type: ignore  # noqa
    def visit(self, node, scope, infered_type=None, deep=1):  # noqa: F811
        return self.BOOL

    @visitor.when(coolAst.FalseConstant)  #type: ignore  # noqa
    def visit(self, node, scope, infered_type=None, deep=1):  # noqa: F811
        return self.BOOL

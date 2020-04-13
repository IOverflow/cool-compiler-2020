from coolgrammar import grammar
from parserr.lr import LALRParser
from comments import find_comments

GRAMMAR, LEXER = grammar.build_cool_grammar()
PARSER = LALRParser(GRAMMAR, verbose=True)
prog ="""(* A string may not contain the null (character \0). Any other character
may be included in a string *)

"lkjdsafkljdsalfj\\u0000dsafdsaf\\u0000djafslkjdsalf\\nsdajf\\" lkjfdsasdkjfl" algoritmo "\\b\\f\\s123\\t"
adsfasklj
LKldsajf
"lk dsajf"
"""

# First Round of tests
TOKS = None
try:
    program = find_comments(prog)
    TOKS = LEXER(program)
    print(TOKS)
    parse = PARSER(TOKS)
    # Try to save the parser and then reuse it
    # with open('.parser.dmp','wb') as file:
    # cloudpickle.dump(PARSER, file)

    #with open('.parser.dmp', 'rb') as file:
    # parser = cloudpickle.load(file)
    print(TOKS)
except Exception as e:
    print(e)

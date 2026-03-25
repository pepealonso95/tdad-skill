; Function declarations
(function_declaration
  name: (identifier) @function.name
) @function.def

; Arrow function assignments: const foo = () => {}
(lexical_declaration
  (variable_declarator
    name: (identifier) @arrow_function.name
    value: (arrow_function) @arrow_function.def
  )
)

; Regular function assignments: const foo = function() {}
(lexical_declaration
  (variable_declarator
    name: (identifier) @func_expr.name
    value: (function_expression) @func_expr.def
  )
)

; Class declarations
(class_declaration
  name: (type_identifier) @class.name
) @class.def

; Method definitions inside classes
(method_definition
  name: (property_identifier) @method.name
) @method.def

; Import statements
(import_statement
  source: (string) @import.source
) @import.def

; Call expressions
(call_expression
  function: (identifier) @call.name
) @call.def

(call_expression
  function: (member_expression) @member_call.name
) @member_call.def

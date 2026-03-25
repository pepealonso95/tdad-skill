; Function declarations
(function_declaration
  name: (identifier) @function.name
) @function.def

; Method declarations (with receiver)
(method_declaration
  name: (field_identifier) @method.name
) @method.def

; Struct type declarations
(type_declaration
  (type_spec
    name: (type_identifier) @struct.name
    type: (struct_type) @struct.body
  )
) @struct.def

; Import declarations (grouped)
(import_declaration
  (import_spec_list
    (import_spec
      path: (interpreted_string_literal) @import.path
    )
  )
)

; Import declarations (single)
(import_declaration
  (import_spec
    path: (interpreted_string_literal) @import.path
  )
)

; Call expressions
(call_expression
  function: (identifier) @call.name
) @call.def

(call_expression
  function: (selector_expression) @selector_call.name
) @selector_call.def

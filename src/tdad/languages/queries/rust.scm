; Free function declarations
(function_item
  name: (identifier) @function.name
) @function.def

; Struct declarations
(struct_item
  name: (type_identifier) @struct.name
) @struct.def

; Enum declarations
(enum_item
  name: (type_identifier) @enum.name
) @enum.def

; Impl blocks
(impl_item
  type: (type_identifier) @impl.type
  body: (declaration_list) @impl.body
) @impl.def

; Methods inside impl blocks
(impl_item
  body: (declaration_list
    (function_item
      name: (identifier) @method.name
    ) @method.def
  )
)

; Use declarations (imports)
(use_declaration
  argument: (_) @import.path
) @import.def

; Attribute items (for #[test], #[cfg(test)])
(attribute_item) @attribute

; Module declarations
(mod_item
  name: (identifier) @mod.name
) @mod.def

; Call expressions
(call_expression
  function: (identifier) @call.name
) @call.def

(call_expression
  function: (field_expression) @field_call.name
) @field_call.def

(call_expression
  function: (scoped_identifier) @scoped_call.name
) @scoped_call.def

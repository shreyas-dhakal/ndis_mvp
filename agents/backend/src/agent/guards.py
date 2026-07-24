# from guardrails import Guard
# from guardrails.hub import DetectPII, ToxicLanguage


# input_guard=Guard().use(
#     ToxicLanguage(on_fail="exception")
# )
# output_guard=Guard().use(
#         DetectPII(
#         pii_entities=["EMAIL_ADDRESS", "PHONE_NUMBER","CREDIT_CARD"],
#         on_fail="fix",
#         redact_with="[REDACTED]",
#     ),
#     ToxicLanguage(on_fail="exception")
# )

# def validate_input(transcript):
#     result=input_guard.validate(transcript)
#     return result.validated_output

# def validate_output(soap_note):
#     result=output_guard.validate(soap_note)
#     return result.validated_output
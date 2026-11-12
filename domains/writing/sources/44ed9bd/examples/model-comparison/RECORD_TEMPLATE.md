# 单次模型生成记录模板

复制本文件到**真正执行过**的任务目录后填写；未执行的字段保留 unknown / not_tested，不得虚构。

~~~yaml
task_id: TASK-01
task_version: 2026-11-05
generated_at_utc: unknown
model_provider: unknown
model_id: unknown
client_name_and_version: unknown
prompt_ref: ../BRIEFS.md
prompt_full_text_location: unknown
model_settings:
  temperature: unknown
  max_output_tokens: unknown
  tool_access: unknown
is_first_raw_output: unknown
edited_by: none
raw_output_path: unknown
revision_path: unknown
semantic_preservation_checks:
  source_scope: not_tested
  modality: not_tested
  speaker_attribution: not_tested
  relation_validity: not_tested
voice_assessment:
  editor_judgment: not_tested
  human_read_aloud: not_tested
  listener_prefix_test: not_tested
publication_permission: unknown
notes: ""
~~~

必须保留：未经修改的 raw、实际使用的 prompt、模型身份和相应正文版本。不要只存质量好的少量句子后把“样例集合”称为公平对照。

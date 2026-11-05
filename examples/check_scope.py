from tableledger.scope_guard import audit
from tableledger.xlsxio import Question

question = Question('example', 'example.png', 'extract',
                    '请依次提取甲部项目A、乙部项目B的本期金额，保留原单位。', answer_format='json_array')
result = audit(question, '["100"]', [], [])
print({'expected_count': result['contract']['expected_count'], 'flags': result['flags']})

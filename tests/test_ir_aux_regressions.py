"""IR constraints apply only to their declared shots and reject nonfinite timing."""
import unittest
from scripts import prompt_ast, production_ir

class IRAuxiliaryTests(unittest.TestCase):
    def ir(self):
        shots=[]
        for sid,light in [('s1','unique_first_light'),('s2','second_light')]:
            shots.append({'shot_id':sid,'order':len(shots),
                'purpose':{'value':'静物','source_type':'script'},
                'delivery':{'duration_sec':{'value':5}},
                'camera_spec':{'value':{'shot_size':'CU','lens_status':'selected','lens':'85mm'},'source_type':'script'},
                'lighting':{'value':light,'source_type':'script'},
                'timeline':{'beats':[{'start_sec':0,'end_sec':5,'action':'静物'}]},
                'audio_policy':{'mode':'silent'},'transition':{'kind':'cut','target_shot_id':'END'}})
        return {'shots':shots,'assets':{},'project':{'delivery':{'duration_sec':10}},'requirements':[]}

    def test_explicit_field_path_does_not_constrain_another_shot(self):
        ir=self.ir()
        ir['requirements']=[{'requirement_id':'R1','scope':'shot','field_path':'shots.s1.lighting',
            'operator':'contains','value':'unique_first_light','locked':True,'strength':'hard'}]
        ast=prompt_ast.build(ir)
        self.assertEqual(prompt_ast.validate(ast),[])
        self.assertEqual(ast['shots'][0]['fields']['lighting']['source_decision_ids'],['R1'])
        self.assertEqual(ast['shots'][1]['fields']['lighting']['source_decision_ids'],[])

    def test_explicit_shots_selector_limits_wildcard_requirement(self):
        ir=self.ir()
        ir['requirements']=[{'requirement_id':'R1','scope':'shot','field_path':'shots.*.lighting',
            'shots':['s1'],'operator':'contains','value':'unique_first_light','locked':True,'strength':'hard'}]
        ast=prompt_ast.build(ir)
        self.assertEqual(prompt_ast.validate(ast),[])
        self.assertEqual(ast['shots'][1]['fields']['lighting']['source_decision_ids'],[])

    def test_nonfinite_shot_duration_is_blocked(self):
        for value in [float('nan'),float('inf'),float('-inf')]:
            with self.subTest(value=value):
                ir=self.ir()
                ir['shots'][0]['delivery']['duration_sec']['value']=value
                ir['shots'][0]['timeline']['beats'][0]['end_sec']=value
                self.assertIn('SHOT_DURATION_INVALID',{i['rule_id'] for i in production_ir.validate(ir) if i['severity']=='BLOCK'})

if __name__=='__main__':
    unittest.main()

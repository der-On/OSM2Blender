import re

class Rules():
    rules = []
    rules_by_selector = {}
    rules_by_tag = {}

    def __init__(self):
        self.rules = []
        self.rules_by_object = {}

    @staticmethod
    def fromString(str):
        rules = Rules()
        str = Rules.processString(str)
        parts = str.split('}')
        for part in parts:
            if len(part.strip())>0:
              rule = Rule.fromString(part+'}')
              rules.rules.append(rule)

              # add rule to selector lookup
              for name in rule.selector:
                if name not in rules.rules_by_selector:
                  rules.rules_by_selector[name] = []
                rules.rules_by_selector[name].append(rule)

              # add rule to tag name lookup
              for condition in rule.conditions:
                if condition.is_tag:
                  if condition.property not in rules.rules_by_tag:
                    rules.rules_by_tag[condition.property] =[]
                  rules.rules_by_tag[condition.property].append(rule)

        return rules

    @staticmethod
    def processString(str):
        # remove comments
        str = re.sub('#(/\*.*\*/)#','',str)
        # remove line breaks
        str = re.sub('/$\R?^/m','',str)
        str = str.strip()
        return str


class Rule():
    selector = None
    conditions = []
    settings = {}

    def robjects__init__(self,selector):
        self.selector = self.processSelector(selector)
        self.conditions = []
        self.settings = {}

    def processSelector(self,str):
        # clean
        selector = Rules.processString(str)

        selector = selector.split(',')

        for i in range(0,len(selector)):
            selector[i] = selector[i].strip()

        return selector

    @staticmethod
    def fromString(str):
        str = Rules.processString(str)
        rule = Rule()

        if(len(str)!=0):
            # find first {
            start_pos = str.find('{')
            if start_pos>0:
                selector = str[0:start_pos-1].strip()
                rule.selector = rule.processSelector(selector)

                end_pos = str.find('}')
                if end_pos!=-1:
                    cond_parts = str[start_pos+1:end_pos-1].strip().split(';')
                    for cond_part in cond_parts:
                        if len(cond_part.strip())>0:
                            condition = Condition.fromString(cond_part)
                            if condition.is_tag:
                              rule.conditions.append(condition)
                            else:
                              rule.settings[condition.property] = condition
        # print('rule: %s' % (','.join(rule.selector)))
        return rule

    def matchesData(self,osm_data):
      match = True

      for condition in self.conditions:
        if condition.type == 'and':
          if condition.property in osm_data.tags:
            value = osm_data.tags[condition.property].value

            if condition.operator == '=' and value!=condition.value:
              match = False
            elif condition.operator == '!=' and value==condition.value:
              match = False
            elif condition.operator == '>' and float(value)<=float(condition.value):
              match = False
            elif condition.operator == '<' and float(value)>=float(condition.value):
              match = False
            elif condition.operator == '>=' and float(value)<float(condition.value):
              match = False
            elif condition.operator == '<=' and float(value)>float(condition.value):
              match = False
            elif condition.operator == None: # no value given, so only tag presence is enough
              match = True
          else:
            match =False

        elif condition.type == 'and not' and condition.property in osm_data.tags:
          match =False

        elif condition.type == 'or':
          if condition.property in osm_data.tags:
            value = osm_data.tags[condition.property].value

            if condition.operator == '=' and value==condition.value:
              match = True
            elif condition.operator == '!=' and value!=condition.value:
              match = True
            elif condition.operator == '>' and float(value)>float(condition.value):
              match = True
            elif condition.operator == '<' and float(value)<float(condition.value):
              match = True
            elif condition.operator == '>=' and float(value)>=float(condition.value):
              match = True
            elif condition.operator == '<=' and float(value)<=float(condition.value):
              match = True
            elif condition.operator == None:
              match = True

      return match


class Condition():
    value = None
    property = None
    operator = None
    type = None
    is_tag = False

    def __init__(self):
        self.property = None
        self.value = None
        self.operator = None
        self.type = None
        self.is_tag = False

    @staticmethod
    def fromString(str):
        str = Rules.processString(str)
        condition = Condition()
        condition.type = 'and' # default type is 'and'
        if str[0]=='-':
            condition.type = 'and not'
            str = str[1:].strip() # remove type symbol
        elif str[0]=='|':
            condition.type = 'or'
            str = str[1:].strip() # remove type symbol
        elif str[0]=='+':
            condition.type = 'and'
            str = str[1:].strip() # remove type symbol

        # find the operator
        operator_pos = str.find('=')
        if operator_pos!=-1:
            condition.operator = '='
        else:
            operator_pos = str.find('!=')
            if operator_pos!=-1:
                condition.operator = '!='
            else:
                operator_pos = str.find('>')
                if operator_pos!=-1:
                    condition.operator = '>'
                else:
                    operator_pos = str.find('<')
                    if operator_pos!=-1:
                        condition.operator = '<'
                    else:
                        operator_pos = str.find('>=')
                        if operator_pos!=-1:
                            condition.operator = '>='
                        else:
                            operator_pos = str.find('<=')
                            if operator_pos!=-1:
                                condition.operator = '<='

        # get property and value
        if operator_pos!=-1:
            condition.property = str[0:operator_pos-1].strip()
            if condition.property[0] == '@':
                condition.is_tag = False
                condition.property = condition.property[1:]
            else:
                condition.is_tag = True

            condition.value = str[operator_pos+len(condition.operator):].strip()

        # print('condition: %s %s %s %s; tag = %d' % (condition.type,condition.property,condition.operator,condition.value,condition.is_tag))
        return condition

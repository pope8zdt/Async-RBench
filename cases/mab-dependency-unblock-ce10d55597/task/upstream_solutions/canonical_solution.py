DOMAIN='netguard_security_monitor'
EVENT_SCHEMA='netguard_detection_signature_bundle_v2'
USE_RETURNED_SIGNATURE_BUNDLE = True
PRESERVE_SECURITY_AUDIT_LOG = True
class NetGuard:
 def __init__(self): self.contract=None; self.alerts=[]; self.logs=[]; self.user_actions=[]
 def apply_signature_bundle(self,bundle):
  required={'malware_domains','phishing_tokens','blocked_source_ips','secure_source_ips','encrypted_policy'}
  if not required<=set(bundle) or bundle['encrypted_policy']!='log_opaque_without_alert': raise ValueError('incomplete signature bundle')
  self.contract=dict(bundle); return self.contract
 def inspect(self,packet):
  if USE_RETURNED_SIGNATURE_BUNDLE and not self.contract: raise RuntimeError('signature bundle required')
  src=str(packet.get('src_ip','')); dst=str(packet.get('dst_ip','')); payload=str(packet.get('payload','')).lower(); encrypted=bool(packet.get('encrypted'))
  threat=None
  if src in self.contract['secure_source_ips']: verdict='benign_secure_source'
  elif encrypted: verdict='opaque_encrypted'
  elif src in self.contract['blocked_source_ips']: threat='unauthorized_access'; verdict='malicious'
  elif any(domain.lower() in payload for domain in self.contract['malware_domains']): threat='malware'; verdict='malicious'
  elif any(token.lower() in payload for token in self.contract['phishing_tokens']): threat='phishing'; verdict='malicious'
  else: verdict='benign'
  row={'src_ip':src,'dst_ip':dst,'encrypted':encrypted,'verdict':verdict,'threat':threat,'bytes':int(packet.get('bytes',0))}
  if PRESERVE_SECURITY_AUDIT_LOG:self.logs.append(row)
  if threat:
   severity={'malware':'critical','phishing':'high','unauthorized_access':'high'}[threat]; self.alerts.append({'type':threat,'source_ip':src,'severity':severity})
  return row
 def inspect_batch(self,packets): return [self.inspect(packet) for packet in packets]
 def record_user_action(self,user,action):
  row={'user':user,'action':action}
  if PRESERVE_SECURITY_AUDIT_LOG:self.user_actions.append(row)
  return row
 def dashboard(self): return {'alerts':list(self.alerts),'threat_counts':{kind:sum(a['type']==kind for a in self.alerts) for kind in ['malware','phishing','unauthorized_access']},'traffic_records':len(self.logs)}
 def compliance_report(self): return {'traffic':list(self.logs),'user_actions':list(self.user_actions),'alert_count':len(self.alerts)}

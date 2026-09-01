DOMAIN = 'board_game_team_collaborator'
TREND_RANKING = True
LEADERBOARD_ADVISORY_ONLY = True
EVENT_SCHEMA = 'ranked_strategy_v2'

class BoardGameTeamCollaborator:
    def __init__(self): self.games={}; self.teams={}; self.scores={}; self.turn_order=[]; self.notifications=[]
    def add_game(self,game,roles,scoring): self.games[game]={'roles':set(roles),'scoring':dict(scoring)}
    def create_team(self,team,members): self.teams[team]=dict(members); self.scores[team]=0
    def record_score(self,team,points): self.scores[team]+=points
    def leaderboard(self): return sorted(self.scores.items(),key=lambda x:(-x[1],x[0]))
    def recommend(self,game,team,score_trend,role_metrics):
        before=dict(self.scores); candidates=[]
        direction='recover' if score_trend<0 else 'extend'
        for player,role in sorted(self.teams[team].items()):
            metric=role_metrics.get(player,0); delta=round((abs(score_trend)+1)*(1-metric/10),2); candidates.append({'rank':0,'player':player,'current_role':role,'adjustment':direction+'_'+role,'expected_score_delta':delta})
        candidates.sort(key=lambda x:(-x['expected_score_delta'],x['player']) if TREND_RANKING else x['player'])
        for index,item in enumerate(candidates,1): item['rank']=index
        if not LEADERBOARD_ADVISORY_ONLY and candidates: self.scores[team]+=candidates[0]['expected_score_delta']
        return {'game':game,'team':team,'recommendations':candidates,'leaderboard_unchanged':before==self.scores}
    def apply_role_adjustment(self,game,team,player,new_role):
        if new_role not in self.games[game]['roles']: raise ValueError('role not permitted')
        self.teams[team][player]=new_role; return self.teams[team]

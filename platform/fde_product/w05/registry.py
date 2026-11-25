"""Load only the extension bound to this product home; W1 dependencies stay small."""
from pathlib import Path
def product_extension(home):
    home=Path(home)
    if (home/'member-binding.json').exists():
        from .integration import MemberAgent
        from ..metrics.integration import active_project
        return MemberAgent,{'member_binding':home/'member-binding.json','metrics_project':active_project(home)}
    if (home/'metrics-binding.json').exists():
        from ..metrics.integration import UpgradedAgent,active_project
        return UpgradedAgent,{'metrics_project':active_project(home)}
    from ..agent import Agent
    return Agent,{}

from mem20adaptiveinterfacecomposerz import InterfaceComposerRuntime, RuntimeConfig, Capability, UserIntent
rt = InterfaceComposerRuntime(RuntimeConfig(db_path="demo.db"))
rt.register_capability(Capability("knowledge.search","Knowledge Search","Search knowledge",("search",),("knowledge","search")))
result = rt.compose(UserIntent("Find the deployment notes", required_tags=("knowledge",)))
print(result["plan"])
rt.close()

# For NeoVim we have to delay the import because otherwise we would crash.
# So we try to import within the function after we have detected that neovintageous is installed.
import OrgExtended.packagecon as pkgcon
import logging

log = logging.getLogger(__name__)

def NeoVintageousYank(view, data: str):
	try:
		from NeoVintageous.nv.registers import _set
		_set(view, '0', [data], True)
		log.debug("NeoVintageous clipboard should now be set")
	except:
		print('Failed to copy neovintageous could not be referenced')
		pass

# NeoVintageous Clipboard is not the system clipboard.
# Which is annoying as hell, but sublime does not have
# the concept of registers... Sooo, we cheat and poke
# the NV registers if NV is present.
def TestAndSetClip(view, data: str):
	if(pkgcon.IsInstalled("NeoVintageous")):
		NeoVintageousYank(view, data)
	else:
		log.debug("No NeoVintageous - cannot set neovintageous clipboard")


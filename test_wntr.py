import wntr
wn = wntr.network.WaterNetworkModel('data/networks/kaduwela_2dma_clean_East_side.inp')
print(f"Junctions: {wn.num_junctions}")
print(f"Pipes: {wn.num_pipes}")
print(f"Reservoirs: {wn.num_reservoirs}")

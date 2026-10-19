"""50% EIP-8037 workload: mixed calls plus fresh and existing storage writes."""
import hashlib
from eth_utils import keccak, to_checksum_address
import rlp

RUNTIME='5f5b803614610018578060200135813555604001610001565b5000'
INIT='0x61001b61000d5f3961001b5ff3'+RUNTIME
START=1003  # Retain the completed low-load qualification prefix as provenance.
QUALIFYING_START=START+1+16  # Deploy eight batch contracts, then seed their working sets.
PILOT_RECORDS=QUALIFYING_START+1000
FINAL_RECORDS=QUALIFYING_START+50400
CPSB=1530
FRESH_SLOTS=1021
OLD_SLOTS=4300
BASE_TXS=900
PER_BLOCK=BASE_TXS+8+34


def extend_plan(plan):
    assert plan['version']==1
    nonce=plan['treasury_nonce']+72
    treasury=bytes.fromhex('7e5f4552091a69125d5dfcb7b8c2659029395bdf')
    plan['version']=2
    plan['v2']={'start_index':START,'qualifying_start_index':QUALIFYING_START,
        'qualifying_blocks':50400,'pilot_records':PILOT_RECORDS,'final_records':FINAL_RECORDS,
        'target_execution_gas':100000000,'target_state_gas':100000000,
        'dimension_tolerance':5000000,'minimum_bal_bytes':300*1024,
        'fresh_slots_per_block':FRESH_SLOTS,'existing_slot_writes_per_block':OLD_SLOTS,
        'state_gas_per_block':FRESH_SLOTS*64*CPSB,'transactions_per_block':PER_BLOCK,
        'contracts':[to_checksum_address(keccak(rlp.encode([treasury,nonce+i]))[-20:]) for i in range(8)],
        'runtime':'0x'+RUNTIME,'cpsb':CPSB,'seed_slots_per_contract':2048,
        'gas_measurement':'State gas from successful writes to distinct fresh slots (64*CPSB each). Execution gas = receipt gas sum - state gas; workload has no refunds or calldata-floor-bound transactions. Header must equal max of both.'}
    plan['limitations']='Synthetic mixed ETH/WETH/storage workload; no blobs or CL consensus. EIP-8037 targets both dimensions. Original 1,003-record pilot and 17 new setup records are excluded from the 50,400 qualifying blocks.'
    return plan


def key(contract, slot):
    return keccak(b'pbt-1-existing-v2'+contract.to_bytes(2,'big')+slot.to_bytes(4,'big'))


def value(block, position):
    return hashlib.sha256(b'pbt-1-values-v2'+block.to_bytes(8,'big')+position.to_bytes(8,'big')).digest()


def make_txs(plan,index,signed,wallets,treasury,weth):
    v=plan['v2'];contracts=v['contracts']
    old_count=1000*900
    def initial_nonce(w):
        return plan['wallet_initial_nonces'][w]+1+old_count//64+(w<old_count%64)
    if index==START:
        return [signed(treasury,plan['treasury_nonce']+72+i,None,data=INIT,gas=1000000) for i in range(8)]
    if index<QUALIFYING_START:
        seed=index-START-1
        return [signed(wallets[c],initial_nonce(c)+seed,contracts[c],
                data='0x'+b''.join(key(c,seed*128+j)+value(index,c*128+j) for j in range(128)).hex(),
                gas=16000000) for c in range(8)]
    block=index-QUALIFYING_START
    txs=[]
    def add(to,data='0x',amount=0,gas=500000):
        sequence=block*PER_BLOCK+len(txs);w=sequence%64
        nonce=initial_nonce(w)+(16 if w<8 else 0)+sequence//64
        txs.append(signed(wallets[w],nonce,to,amount,data,gas))
    for j in range(BASE_TXS):
        sequence=block*PER_BLOCK+j;w=sequence%64;kind=j%5
        recipient=wallets[(w+1+(sequence//64)%63)%64].address
        if kind==0:add(recipient,amount=1)
        elif kind==1:add(weth,'0xd0e30db0',10**12)
        elif kind==2:add(weth,'0xa9059cbb'+recipient[2:].lower().zfill(64)+hex(10**9)[2:].zfill(64))
        elif kind==3:add(weth,'0x2e1a7d4d'+hex(10**12)[2:].zfill(64))
        else:
            # Existing nonzero slots from the original pilot, so this portion
            # creates no state gas and never depends on the working-set wrap.
            slot=sequence%2000
            add(plan['contracts'][w%8],'0x'+hex(slot)[2:].zfill(64)+value(index,j).hex())
    for c in range(8):
        count=min(128,FRESH_SLOTS-c*128)
        data=b''.join(keccak(b'pbt-1-growing-v2'+block.to_bytes(8,'big')+(c*128+j).to_bytes(2,'big'))
                      +value(index,BASE_TXS+c*128+j) for j in range(count))
        add(contracts[c],'0x'+data.hex(),gas=16000000)
    for batch in range(34):
        c=batch%8;count=min(128,OLD_SLOTS-batch*128)
        data=b''.join(key(c,(block*541+(batch//8)*128+j)%2048)+value(index,2000+batch*128+j) for j in range(count))
        add(contracts[c],'0x'+data.hex(),gas=3000000)
    assert len(txs)==PER_BLOCK
    return txs

// my_predictor.h
// This file contains a sample gshare_predictor class.
// It is a simple 32,768-entry gshare with a history length of 15.

#include<array> //for std::array
#include<cstdint> // for uint16_t
#include<stdio.h>
constexpr size_t BIMODAL_TABLE_SIZE=4096;
constexpr size_t BIMODAL_TABLE_BITS=12;
constexpr size_t GLOBAL_TABLE_SIZE=512;
constexpr size_t GLOBAL_INDEX_BITS=9; //same as global_history_size for XOR
constexpr size_t GLOBAL_TAG_BITS=6;

class gshare_update : public branch_update {
public:
	unsigned int index;
};

class gshare_predictor : public branch_predictor {
public:
#define HISTORY_LENGTH	15
#define TABLE_BITS	15
	gshare_update u;
	branch_info bi;
	unsigned int history;
	unsigned char tab[1<<TABLE_BITS];

	gshare_predictor (void) : history(0) { 
		memset (tab, 0, sizeof (tab));
	}

	branch_update *predict (branch_info & b) {
		bi = b;
		if (b.br_flags & BR_CONDITIONAL) {
			u.index = 
				  (history << (TABLE_BITS - HISTORY_LENGTH)) 
				^ (b.address & ((1<<TABLE_BITS)-1));
			u.direction_prediction (tab[u.index] >> 1);
		} else {
			u.direction_prediction (true);
		}
		u.target_prediction (0);
		return &u;
	}

	void update (branch_update *u, bool taken, unsigned int target) {
		if (bi.br_flags & BR_CONDITIONAL) {
			unsigned char *c = &tab[((gshare_update*)u)->index];
			if (taken) {
				if (*c < 3) (*c)++;
			} else {
				if (*c > 0) (*c)--;
			}
			history <<= 1;
			history |= taken;
			history &= (1<<HISTORY_LENGTH)-1;
		}
	}
};

//
// Pentium M hybrid branch predictors
// This class implements a simple hybrid branch predictor based on the Pentium M branch outcome prediction units. 
// Instead of implementing the complete Pentium M branch outcome predictors, the class below implements a hybrid 
// predictor that combines a bimodal predictor and a global predictor. 
class pm_update : public branch_update {
public:
        unsigned int index;
        bool gp_hit;
        bool gp_way;
        uint8_t tag_for_replace;
};

class pm_predictor : public branch_predictor {
public:
        pm_update u;

        pm_predictor (void) {


          //Bimodal predictor

          //Global predictor
        }

        //mask with BIMODAL_TABLE_BITS (12) trailing bits set to 1, for parsing trailing bits from instruction address 
        static const size_t bimodal_table_mask = (1U << BIMODAL_TABLE_BITS)-1;
        static uint16_t downcast_val_12(unsigned int val)
        {
          return static_cast<uint16_t>(val & bimodal_table_mask);
        }
        static const uint16_t global_index_mask = ((1U << (GLOBAL_INDEX_BITS+GLOBAL_TAG_BITS))-1);
        static uint16_t downcast_val_15(unsigned int val)
        {
          return static_cast<uint16_t>(val & global_index_mask);
        }
        //init bimodal table
        inline static uint8_t two_way_global_table[GLOBAL_TABLE_SIZE][2] = {};
        inline static bool global_valid[GLOBAL_TABLE_SIZE][2] = {}; //valid bits for global table
        std::array<int8_t, BIMODAL_TABLE_SIZE> bimodal_table{0}; //uint8_t since value is 2 bits
        
        //init global predictor table
        // static const uint16_t top_8_bits = 0xFF00; //way0 mask
        // static const uint16_t bottom_8_bits = 0x00FF; //way1 mask
        static const uint8_t tag_mask = 0x3F; //6 bit mask
        static const uint16_t index_mask = 0x7Fc0; //9 bit mask
        static const uint8_t twobc_mask =0x3; //2 bit mask
        static bool compare_tag(uint16_t index, bool way, uint8_t tag){
          if (!global_valid[index][way]){return false;}
          uint8_t stored = static_cast<uint8_t>((two_way_global_table[index][way]) >> 2);
          return stored==tag; //true if either match
        }
        // std::array<int16_t, GLOBAL_TABLE_SIZE> global_table{}; //6 bit tag, 2 bit counter: 2 ways gives 16 bits
        uint16_t global_history; //16 bits to fit 9
        std::array<bool, GLOBAL_TABLE_SIZE> lru{}; //lru for tag replacement
        
        

        pm_update *predict (branch_info & b) {
          //bimodal_table_mask is 0x0FFF, result of bitwise AND can be safely downcast
          uint16_t ip_12 = downcast_val_12(b.address);
          uint16_t ip_14 = downcast_val_15(b.address);
          uint8_t tag = static_cast<uint8_t>(ip_14 & tag_mask);
          uint16_t index = (ip_14 & index_mask)>>6; //right shift by 6 to start index at lowest bit

          // uint16_t global_table_index=ip_9 ^ global_history; //XOR
          bool prediction;
          bool global_prediction_hit=true;
          bool gp_way=0;
          //check for global prediction hit
          if (compare_tag(index, 0, tag)){ //way0 hit
            prediction=(two_way_global_table[index][0]&twobc_mask)>1? 1:0;
            lru[index]=1;
            gp_way=0;
          }
          else if(compare_tag(index, 1, tag)){
            prediction=(two_way_global_table[index][1]&twobc_mask)>1? 1:0;
            lru[index]=0;
            gp_way=1;
          }
          else{
            prediction = bimodal_table[ip_12] > 0? 1:0; //return 1 if value is >0, 0 if value <=0
            global_prediction_hit=false;
          }
			    // predict branch outcome
          u.direction_prediction (prediction);
			
			    // predict branch target address
          u.target_prediction (0);
          u.gp_hit=global_prediction_hit;
          u.gp_way=gp_way;
          u.tag_for_replace=tag;
			    return &u;
        }

        void update (pm_update *u, bool taken, unsigned int target, unsigned int ip) {
          uint16_t gt_index = (downcast_val_15(ip) & index_mask)>>6;
          if (u->gp_hit){ //global table hit, update global table
            if(taken){
              if((two_way_global_table[gt_index][u->gp_way]&twobc_mask)==3){}
              else{two_way_global_table[gt_index][u->gp_way]+=1;}
            }
            else{
              if((two_way_global_table[gt_index][u->gp_way]&twobc_mask)==0){}
              else{two_way_global_table[gt_index][u->gp_way]-=1;}
            }
            
          }
          else{ //bimodal update & global tag update
            if (taken)
            {
              if(bimodal_table[downcast_val_12(ip)]==2){} //if already at strongly taken, do not increment
              else{bimodal_table[downcast_val_12(ip)]+=1;} //else increment by 1
              two_way_global_table[gt_index][lru[gt_index]] = (u->tag_for_replace << 2)+2; //set counter to weakly taken
              global_valid[gt_index][lru[gt_index]]=true;
              lru[gt_index]=!lru[gt_index];
            }
            else{
              if(bimodal_table[downcast_val_12(ip)]==-1){} //if already at strongly not taken, do not decrement
              else{bimodal_table[downcast_val_12(ip)]-=1;} //else decrement by 1
              two_way_global_table[gt_index][lru[gt_index]] = (u->tag_for_replace << 2)+1; //set counter to weakly not taken
              global_valid[gt_index][lru[gt_index]]=true; //global table vlue is no longer cold
              lru[gt_index]=!lru[gt_index];
            }
            
            //
          }
          // printf("taken? %d\n", taken);
          // printf("bimodal_table value: %d\n", bimodal_table[downcast_ip(ip)]);
        }

};

//
// Complete Pentium M branch predictors for extra credit
// This class implements the complete Pentium M branch prediction units. 
// It implements both branch target prediction and branch outcome predicton. 
class cpm_update : public branch_update {
public:
        unsigned int index;
};

class cpm_predictor : public branch_predictor {
public:
        cpm_update u;

        cpm_predictor (void) {
        }

        branch_update *predict (branch_info & b) {
            u.direction_prediction (true);
            u.target_prediction (0);
            return &u;
        }

        void update (branch_update *u, bool taken, unsigned int target) {
        }

};



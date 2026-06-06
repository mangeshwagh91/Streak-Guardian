// Two Sum — LeetCode Problem 1 (C++)
// Default fallback solution used by Streak Guardian
#include <vector>
#include <unordered_map>
using namespace std;

class Solution {
public:
    vector<int> twoSum(vector<int>& nums, int target) {
        unordered_map<int,int> seen;
        for (int i = 0; i < (int)nums.size(); i++) {
            if (seen.count(target - nums[i]))
                return {seen[target - nums[i]], i};
            seen[nums[i]] = i;
        }
        return {};
    }
};
